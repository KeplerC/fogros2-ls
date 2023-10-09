use crate::api_server::ROSTopicRequest;
use crate::connection_fib::connection_fib_handler;

#[cfg(feature = "ros")]
use crate::network::webrtc::{register_webrtc_stream, webrtc_reader_and_writer};

use crate::pipeline::construct_gdp_forward_from_bytes;
use crate::structs::{
    gdp_name_to_string, generate_random_gdp_name, get_gdp_name_from_topic, GDPName, GdpAction,
    Packet,
};

use crate::connection_fib::{FibChangeAction, FibStateChange};
use serde::{Deserialize, Serialize};

use std::env;
use std::sync::{Arc, Mutex};
use tokio::select;
use tokio::sync::mpsc::{UnboundedReceiver, UnboundedSender};


use crate::db::*;
use futures::{StreamExt};
use redis_async::{client, resp::FromResp};

use tokio::sync::mpsc::{self};

use tokio::time::Duration;

pub struct TopicModificationRequest {
    action: FibChangeAction,
    stream: Option<async_datachannel::DataStream>,
    topic_name: String,
    topic_type: String,
    certificate: Vec<u8>,
}


// ROS subscriber -> webrtc (publish remotely)
pub async fn ros_topic_remote_publisher_handler(
    mut status_recv: UnboundedReceiver<TopicModificationRequest>,
) {
    let mut join_handles = vec![];

    let (fib_tx, fib_rx) = mpsc::unbounded_channel();
    let (channel_tx, channel_rx) = mpsc::unbounded_channel();
    let fib_handle = tokio::spawn(async move {
        connection_fib_handler(fib_rx, channel_rx).await;
    });
    join_handles.push(fib_handle);


    let ctx = r2r::Context::create().expect("context creation failure");
    let node = Arc::new(Mutex::new(
        r2r::Node::create(ctx, "sgc_remote_publisher", "namespace").expect("node creation failure"),
    ));

    let ros_manager_node_clone = node.clone();
    let _handle = tokio::task::spawn_blocking(move || loop {
        // std::thread::sleep(std::time::Duration::from_millis(100));
        ros_manager_node_clone
            .clone()
            .lock()
            .unwrap()
            .spin_once(std::time::Duration::from_millis(10));
    });

    let mut existing_topics = vec!();

    loop {
        tokio::select! {
            Some(request) = status_recv.recv() => {
                let topic_name = request.topic_name;
                let topic_type = request.topic_type;
                let action = request.action;
                let certificate = request.certificate;
                let fib_tx = fib_tx.clone();
                let topic_gdp_name = GDPName(get_gdp_name_from_topic(
                    &topic_name,
                    &topic_type,
                    &certificate,
                ));

                if request.action != FibChangeAction::ADD {
                    let channel_update_msg = FibStateChange {
                        action: request.action,
                        topic_gdp_name: topic_gdp_name,
                        forward_destination: None,
                    };
                    let _ = channel_tx.send(channel_update_msg);
                    continue;
                }

                let stream = request.stream.unwrap();
                let manager_node = node.clone();

                info!(
                    "[ros_topic_remote_publisher_handler] topic creator for topic {}, type {}, action {:?}",
                    topic_name, topic_type, action
                );

                // ROS subscriber -> FIB -> RTC
                let (ros_tx, _ros_rx) = mpsc::unbounded_channel();
                let (rtc_tx, rtc_rx) = mpsc::unbounded_channel();
                let channel_update_msg = FibStateChange {
                    action: FibChangeAction::ADD,
                    topic_gdp_name: topic_gdp_name,
                    forward_destination: Some(rtc_tx),
                };
                let _ = channel_tx.send(channel_update_msg);


                let rtc_handle = tokio::spawn(webrtc_reader_and_writer(stream, ros_tx.clone(), rtc_rx)); //ros_tx not used, no need to transmit to ROS
                join_handles.push(rtc_handle);

                if existing_topics.contains(&topic_gdp_name) {
                    info!("topic {:?} already exists in existing topics; don't need to create another subscriber", topic_gdp_name);
                } else {
                    existing_topics.push(topic_gdp_name);
                    let mut subscriber = manager_node.lock().unwrap()
                    .subscribe_untyped(&topic_name, &topic_type, r2r::QosProfile::default())
                    .expect("topic subscribing failure");
                    let ros_handle = tokio::spawn(async move {
                        info!("ROS handling loop has started!");
                        while let Some(packet) = subscriber.next().await {
                            info!("received a ROS packet {:?}", packet);
                            let ros_msg = packet;
                            let packet = construct_gdp_forward_from_bytes(topic_gdp_name, topic_gdp_name, ros_msg );
                            fib_tx.send(packet).expect("send for ros subscriber failure");
                        }
                    });
                    join_handles.push(ros_handle);
                }   
            }
        }
    }
}

// webrtc -> ROS publisher (publish locally)
pub async fn ros_topic_remote_subscriber_handler(
    mut status_recv: UnboundedReceiver<TopicModificationRequest>,
) {
    info!("ros_topic_remote_subscriber_handler has started");
    let mut join_handles = vec![];

    let (fib_tx, fib_rx) = mpsc::unbounded_channel();
    let (channel_tx, channel_rx) = mpsc::unbounded_channel();
    let fib_handle = tokio::spawn(async move {
        connection_fib_handler(fib_rx, channel_rx).await;
    });
    join_handles.push(fib_handle);


    let ctx = r2r::Context::create().expect("context creation failure");
    let node = Arc::new(Mutex::new(
        r2r::Node::create(ctx, "sgc_remote_subscriber", "namespace")
            .expect("node creation failure"),
    ));

    let ros_manager_node_clone = node.clone();
    let _handle = tokio::task::spawn_blocking(move || loop {
        // std::thread::sleep(std::time::Duration::from_millis(100));
        ros_manager_node_clone
            .clone()
            .lock()
            .unwrap()
            .spin_once(std::time::Duration::from_millis(1));
    });


    let mut existing_topics = vec!();

    loop {
        tokio::select! {
            Some(request) = status_recv.recv() => {
                let topic_name = request.topic_name;
                let topic_type = request.topic_type;
                let action = request.action;
                let certificate = request.certificate;
                let fib_tx = fib_tx.clone();
                let topic_gdp_name = GDPName(get_gdp_name_from_topic(
                    &topic_name,
                    &topic_type,
                    &certificate,
                ));

                if request.action != FibChangeAction::ADD {
                    let channel_update_msg = FibStateChange {
                        action: request.action,
                        topic_gdp_name: topic_gdp_name,
                        forward_destination: None,
                    };
                    let _ = channel_tx.send(channel_update_msg);
                    continue;
                }

                let stream = request.stream.unwrap();
                let manager_node = node.clone();


                info!(
                    "[ros_topic_remote_subscriber_handler] topic creator for topic {}, type {}, action {:?}",
                    topic_name, topic_type, action
                );


                // RTC -> FIB -> ROS publisher
                let (ros_tx, mut ros_rx) = mpsc::unbounded_channel();
                let (_rtc_tx, rtc_rx) = mpsc::unbounded_channel();

                let channel_update_msg = FibStateChange {
                    action: FibChangeAction::ADD,
                    topic_gdp_name: topic_gdp_name,
                    forward_destination: Some(ros_tx),
                };
                let _ = channel_tx.send(channel_update_msg);


                let rtc_handle = tokio::spawn(webrtc_reader_and_writer(stream, fib_tx.clone(), rtc_rx));
                join_handles.push(rtc_handle);

                if existing_topics.contains(&topic_gdp_name) {
                    info!("topic {:?} already exists in existing topics; don't need to create another publisher", topic_gdp_name);
                } else {
                    existing_topics.push(topic_gdp_name);
                    let publisher = manager_node.lock().unwrap()
                    .create_publisher_untyped(&topic_name, &topic_type, r2r::QosProfile::default())
                    .expect("topic publisher create failure");

                    let ros_handle = tokio::spawn(async move {
                        info!("[ros_topic_remote_subscriber_handler] ROS handling loop has started!");
                        loop{
                            let pkt_to_forward = ros_rx.recv().await.expect("ros_topic_remote_subscriber_handler crashed!!");
                            if pkt_to_forward.action == GdpAction::Forward {
                                info!("new payload to publish");
                                if pkt_to_forward.gdpname == topic_gdp_name {
                                    let payload = pkt_to_forward.get_byte_payload().unwrap();
                                    //let ros_msg = serde_json::from_str(str::from_utf8(payload).unwrap()).expect("json parsing failure");
                                    // info!("the decoded payload to publish is {:?}", ros_msg);
                                    publisher.publish(payload.clone()).unwrap();
                                } else{
                                    info!("{:?} received a packet for name {:?}",pkt_to_forward.gdpname, topic_gdp_name);
                                }
                            }
                        }
                    });
                    join_handles.push(ros_handle);
                }
                
            }
        }
    }
}


async fn create_new_remote_publisher(
    topic_gdp_name: GDPName, topic_name: String, topic_type: String, certificate: Vec<u8>,
    topic_operation_tx: UnboundedSender<TopicModificationRequest>,
) {
    let redis_url = get_redis_url();
    allow_keyspace_notification(&redis_url).expect("unable to allow keyspace notification");
    let publisher_listening_gdp_name = generate_random_gdp_name();

    // currently open another synchronous connection for put and get
    let publisher_topic = format!("{}-pub", gdp_name_to_string(topic_gdp_name));
    let subscriber_topic = format!("{}-sub", gdp_name_to_string(topic_gdp_name));

    let redis_addr_and_port = get_redis_address_and_port();
    let pubsub_con = client::pubsub_connect(redis_addr_and_port.0, redis_addr_and_port.1)
        .await
        .expect("Cannot connect to Redis");
    let topic = format!("__keyspace@0__:{}", subscriber_topic);
    let mut msgs = pubsub_con
        .psubscribe(&topic)
        .await
        .expect("Cannot subscribe to topic");

    let subscribers = get_entity_from_database(&redis_url, &subscriber_topic)
        .expect("Cannot get subscriber from database");
    info!("subscriber list {:?}", subscribers);

    let tasks = subscribers.clone().into_iter().map(|subscriber| {
        let topic_name_clone = topic_name.clone();
        let topic_type_clone = topic_type.clone();
        let certificate_clone = certificate.clone();
        let publisher_topic = publisher_topic.clone();
        let topic_operation_tx = topic_operation_tx.clone();
        let redis_url = redis_url.clone();
        let publisher_listening_gdp_name_clone = publisher_listening_gdp_name.clone();

        tokio::spawn(async move {
            info!("subscriber {}", subscriber);
            let publisher_url = format!(
                "{},{},{}",
                gdp_name_to_string(topic_gdp_name),
                gdp_name_to_string(publisher_listening_gdp_name_clone),
                subscriber
            );
            info!("publisher listening for signaling url {}", publisher_url);

            add_entity_to_database_as_transaction(&redis_url, &publisher_topic, &publisher_url)
                .expect("Cannot add publisher to database");
            info!(
                "publisher {} added to database of channel {}",
                &publisher_url, publisher_topic
            );

            let webrtc_stream = register_webrtc_stream(&publisher_url, None).await;
            info!("publisher registered webrtc stream");
            let topic_creator_request = TopicModificationRequest {
                action: FibChangeAction::ADD,
                stream: Some(webrtc_stream),
                topic_name: topic_name_clone,
                topic_type: topic_type_clone,
                certificate: certificate_clone,
            };
            let _ = topic_operation_tx.send(topic_creator_request);
        })
    });
    let mut tasks = tasks.collect::<Vec<_>>();

    let message_handling_task_handle = tokio::spawn(async move {
        loop {
            let message = msgs.next().await;
            match message {
                Some(message) => {
                    let received_operation = String::from_resp(message.unwrap()).unwrap();
                    info!("KVS {}", received_operation);
                    if received_operation != "lpush" {
                        info!("the operation is not lpush, ignore");
                        continue;
                    }
                    let updated_subscribers =
                        get_entity_from_database(&redis_url, &subscriber_topic)
                            .expect("Cannot get subscriber from database");
                    info!(
                        "get a list of subscribers from KVS {:?}",
                        updated_subscribers
                    );
                    let subscriber = updated_subscribers.first().unwrap(); // first or last?
                    if subscribers.clone().contains(subscriber) {
                        warn!("subscriber {} already in the list, ignore", subscriber);
                        continue;
                    }
                    let publisher_url = format!(
                        "{},{},{}",
                        gdp_name_to_string(topic_gdp_name),
                        gdp_name_to_string(publisher_listening_gdp_name),
                        subscriber
                    );
                    info!("publisher listening for signaling url {}", publisher_url);

                    add_entity_to_database_as_transaction(
                        &redis_url,
                        &publisher_topic,
                        &publisher_url,
                    )
                    .expect("Cannot add publisher to database");
                    info!(
                        "publisher {} added to database of channel {}",
                        &publisher_url, publisher_topic
                    );

                    let webrtc_stream = register_webrtc_stream(&publisher_url, None).await;
                    info!("publisher registered webrtc stream");
                    let topic_name_clone = topic_name.clone();
                    let topic_type_clone = topic_type.clone();
                    let certificate_clone = certificate.clone();
                    let _publisher_topic = publisher_topic.clone();
                    let topic_operation_tx = topic_operation_tx.clone();
                    let topic_creator_request = TopicModificationRequest {
                        action: FibChangeAction::ADD,
                        stream: Some(webrtc_stream),
                        topic_name: topic_name_clone,
                        topic_type: topic_type_clone,
                        certificate: certificate_clone,
                    };
                    let _ = topic_operation_tx.send(topic_creator_request);
                }
                None => {
                    info!("message is none");
                }
            }
        }
    });
    tasks.push(message_handling_task_handle);

    // Wait for all tasks to complete
    futures::future::join_all(tasks).await;
    info!("all the subscribers are checked!");
}

async fn create_new_remote_subscriber(
    topic_gdp_name: GDPName, topic_name: String, topic_type: String, certificate: Vec<u8>,
    topic_operation_tx: UnboundedSender<TopicModificationRequest>,
) {
    let subscriber_listening_gdp_name = generate_random_gdp_name();
    let redis_url = get_redis_url();
    allow_keyspace_notification(&redis_url).expect("unable to allow keyspace notification");
    // currently open another synchronous connection for put and get
    let publisher_topic = format!("{}-pub", gdp_name_to_string(topic_gdp_name));
    let subscriber_topic = format!("{}-sub", gdp_name_to_string(topic_gdp_name));

    let redis_addr_and_port = get_redis_address_and_port();
    let pubsub_con = client::pubsub_connect(redis_addr_and_port.0, redis_addr_and_port.1)
        .await
        .expect("Cannot connect to Redis");
    let topic = format!("__keyspace@0__:{}", publisher_topic);
    let mut msgs = pubsub_con
        .psubscribe(&topic)
        .await
        .expect("Cannot subscribe to topic");

    add_entity_to_database_as_transaction(
        &redis_url,
        &subscriber_topic,
        gdp_name_to_string(subscriber_listening_gdp_name).as_str(),
    )
    .expect("Cannot add publisher to database");
    info!("subscriber added to database");

    let publishers = get_entity_from_database(&redis_url, &publisher_topic)
        .expect("Cannot get subscriber from database");
    info!("publisher list {:?}", publishers);

    let tasks = publishers.clone().into_iter().map(|publisher| {
        let topic_name_clone = topic_name.clone();
        let topic_type_clone = topic_type.clone();
        let certificate_clone = certificate.clone();
        let topic_operation_tx = topic_operation_tx.clone();
        let subscriber_listening_gdp_name_clone = subscriber_listening_gdp_name.clone();
        if !publisher.ends_with(&gdp_name_to_string(subscriber_listening_gdp_name_clone)) {
            info!(
                "find publisher mailbox {} doesn not end with subscriber {}",
                publisher,
                gdp_name_to_string(subscriber_listening_gdp_name_clone)
            );
            let handle = tokio::spawn(async move {});
            return handle;
        } else {
            info!(
                "find publisher mailbox {} ends with subscriber {}",
                publisher,
                gdp_name_to_string(subscriber_listening_gdp_name_clone)
            );
        }
        let publisher = publisher
            .split(',')
            .skip(4)
            .take(4)
            .collect::<Vec<&str>>()
            .join(",");

        tokio::spawn(async move {
            info!("publisher {}", publisher);
            // subscriber's address
            let my_signaling_url = format!(
                "{},{},{}",
                gdp_name_to_string(topic_gdp_name),
                gdp_name_to_string(subscriber_listening_gdp_name_clone),
                publisher
            );
            // publisher's address
            let peer_dialing_url = format!(
                "{},{},{}",
                gdp_name_to_string(topic_gdp_name),
                publisher,
                gdp_name_to_string(subscriber_listening_gdp_name)
            );
            // let subsc = format!("{}/{}", gdp_name_to_string(publisher_listening_gdp_name), subscriber);
            info!(
                "subscriber uses signaling url {} that peers to {}",
                my_signaling_url, peer_dialing_url
            );
            // workaround to prevent subscriber from dialing before publisher is listening
            tokio::time::sleep(Duration::from_millis(1000)).await;
            info!("subscriber starts to register webrtc stream");
            let webrtc_stream =
                register_webrtc_stream(&my_signaling_url, Some(peer_dialing_url)).await;
            info!("subscriber registered webrtc stream");

            let topic_creator_request = TopicModificationRequest {
                action: FibChangeAction::ADD,
                stream: Some(webrtc_stream),
                topic_name: topic_name_clone,
                topic_type: topic_type_clone,
                certificate: certificate_clone,
            };
            let _ = topic_operation_tx.send(topic_creator_request);
        })
    });

    // Wait for all tasks to complete
    futures::future::join_all(tasks).await;
    info!("all the mailboxes are checked!");

    loop {
        tokio::select! {
            Some(message) = msgs.next() => {
                match message {
                    Ok(message) => {
                        let received_operation = String::from_resp(message).unwrap();
                        info!("KVS {}", received_operation);
                        if received_operation != "lpush" {
                            info!("the operation is not lpush, ignore");
                            continue;
                        }

                        let updated_publishers = get_entity_from_database(&redis_url, &publisher_topic).expect("Cannot get publisher from database");
                        info!("get a list of publishers from KVS {:?}", updated_publishers);
                        let publisher = updated_publishers.first().unwrap(); //first or last?

                        if publishers.contains(publisher) {
                            warn!("publisher {} already exists", publisher);
                            continue;
                        }

                        if !publisher.ends_with(&gdp_name_to_string(subscriber_listening_gdp_name)) {
                            warn!("find publisher mailbox {} doesn not end with subscriber {}", publisher, gdp_name_to_string(subscriber_listening_gdp_name));
                            continue;
                        }
                        let publisher = publisher.split(',').skip(4).take(4).collect::<Vec<&str>>().join(",");

                        // subscriber's address
                        let my_signaling_url = format!("{},{},{}", gdp_name_to_string(topic_gdp_name),gdp_name_to_string(subscriber_listening_gdp_name), publisher);
                        // publisher's address
                        let peer_dialing_url = format!("{},{},{}", gdp_name_to_string(topic_gdp_name),publisher, gdp_name_to_string(subscriber_listening_gdp_name));
                        // let subsc = format!("{}/{}", gdp_name_to_string(publisher_listening_gdp_name), subscriber);
                        info!("subscriber uses signaling url {} that peers to {}", my_signaling_url, peer_dialing_url);
                        tokio::time::sleep(Duration::from_millis(1000)).await;
                        info!("subscriber starts to register webrtc stream");
                        // workaround to prevent subscriber from dialing before publisher is listening
                        let webrtc_stream = register_webrtc_stream(&my_signaling_url, Some(peer_dialing_url)).await;

                        info!("subscriber registered webrtc stream");
                        let topic_name_clone = topic_name.clone();
                        let topic_type_clone = topic_type.clone();
                        let certificate_clone = certificate.clone();
                        let topic_operation_tx = topic_operation_tx.clone();
                        let topic_creator_request = TopicModificationRequest {
                            action: FibChangeAction::ADD,
                            stream: Some(webrtc_stream),
                            topic_name: topic_name_clone,
                            topic_type: topic_type_clone,
                            certificate:certificate_clone,
                        };
                        let _ = topic_operation_tx.send(topic_creator_request);
                    },
                    Err(e) => {
                        eprintln!("ERROR: {}", e);
                    }
                }
            }
        }
    }
}

#[derive(Debug, PartialEq, Serialize, Deserialize, Clone)]
pub struct RosTopicStatus {
    pub action: String,
}

pub async fn ros_topic_manager(mut topic_request_rx: UnboundedReceiver<ROSTopicRequest>) {
    let mut waiting_rib_handles = vec![];

    // TODO: now it's hardcoded, make it changable later
    let crypto_name = "test_cert";
    let crypto_path = match env::var_os("SGC_CRYPTO_PATH") {
        Some(config_file) => {
            config_file.into_string().unwrap()
        },
        None => format!(
            "./sgc_launch/configs/crypto/{}/{}-private.pem",
            crypto_name, crypto_name
        ),
    };
    
    let certificate = std::fs::read(crypto_path)
    .expect("crypto file not found!");


    let (publisher_operation_tx, publisher_operation_rx) = mpsc::unbounded_channel();
    let topic_creator_handle = tokio::spawn(async move {
        ros_topic_remote_publisher_handler(publisher_operation_rx).await;
    });
    waiting_rib_handles.push(topic_creator_handle);

    let (subscriber_operation_tx, subscriber_operation_rx) = mpsc::unbounded_channel();
    let topic_creator_handle = tokio::spawn(async move {
        // This is because the ROS node creation is not thread safe 
        // See: https://github.com/ros2/rosbag2/issues/329
        std::thread::sleep(std::time::Duration::from_millis(500));
        ros_topic_remote_subscriber_handler(subscriber_operation_rx).await;
    });
    waiting_rib_handles.push(topic_creator_handle);

    loop {
        select! {
            Some(payload) = topic_request_rx.recv() => {
                // info!("ros topic manager get payload: {:?}", payload);
                match payload.api_op.as_str() {
                    "add" => {

                        let topic_name = payload.topic_name;
                        let topic_type = payload.topic_type;
                        let action = payload.ros_op;

                        // if topic_status.contains_key(&topic_name) {
                        //     info!(
                        //         "topic {} already exist {:?}",
                        //         topic_name, topic_status
                        //     );
                        //     continue;
                        // }

                        let topic_gdp_name = GDPName(get_gdp_name_from_topic(
                            &topic_name,
                            &topic_type,
                            &certificate,
                        ));
                        info!("detected a new topic {:?} with action {:?}, topic gdpname {:?}", topic_name, action, topic_gdp_name);
                        match action.as_str() {
                            // locally subscribe, globally publish
                            "pub" => {
                                let topic_name_cloned = topic_name.clone();
                                let certificate = certificate.clone();
                                let topic_operation_tx = publisher_operation_tx.clone();
                                let handle = tokio::spawn(
                                    async move {
                                        create_new_remote_publisher(topic_gdp_name, topic_name_cloned, topic_type, certificate,
                                            topic_operation_tx).await;
                                    }
                                );
                                waiting_rib_handles.push(handle);
                            }

                            // locally publish, globally subscribe
                            "sub" => {
                                // subscribe to a pattern that matches the key you're interested in
                                // create a new thread to handle that listens for the topic
                                let topic_name_cloned = topic_name.clone();
                                let certificate = certificate.clone();
                                let topic_type = topic_type.clone();
                                let topic_operation_tx = subscriber_operation_tx.clone();
                                let handle = tokio::spawn(
                                    async move {
                                        create_new_remote_subscriber(topic_gdp_name, topic_name_cloned, topic_type, certificate, topic_operation_tx).await;
                                    }
                                );
                                waiting_rib_handles.push(handle);
                            }
                            _ => {
                                warn!("unknown action {}", action);
                            }
                        }
                    },
                    "del" => {
                        info!("deleting topic {:?}", payload);
                        
                        match payload.ros_op.as_str() {
                            "pub" => {
                                let topic_operation_tx = publisher_operation_tx.clone();
                                let topic_creator_request = TopicModificationRequest {
                                    action: FibChangeAction::DELETE,
                                    stream: None,
                                    topic_name: payload.topic_name,
                                    topic_type: payload.topic_type,
                                    certificate: certificate.clone(),
                                };
                                let _ = topic_operation_tx.send(topic_creator_request);

                            }, 
                            "sub" => {
                                let topic_operation_tx = subscriber_operation_tx.clone();
                                let topic_creator_request = TopicModificationRequest {
                                    action: FibChangeAction::DELETE,
                                    stream: None,
                                    topic_name: payload.topic_name,
                                    topic_type: payload.topic_type,
                                    certificate: certificate.clone(),
                                };
                                let _ = topic_operation_tx.send(topic_creator_request);
                            }
                            _ => {
                                warn!("unknown action {}", payload.ros_op);
                            }
                        }
                    },               
                    "resume" => {
                        info!("resuming topic {:?}", payload);
                        
                        match payload.ros_op.as_str() {
                            "pub" => {
                                let topic_operation_tx = publisher_operation_tx.clone();
                                let topic_creator_request = TopicModificationRequest {
                                    action: FibChangeAction::RESUME,
                                    stream: None,
                                    topic_name: payload.topic_name,
                                    topic_type: payload.topic_type,
                                    certificate: certificate.clone(),
                                };
                                let _ = topic_operation_tx.send(topic_creator_request);

                            }, 
                            "sub" => {
                                let topic_operation_tx = subscriber_operation_tx.clone();
                                let topic_creator_request = TopicModificationRequest {
                                    action: FibChangeAction::RESUME,
                                    stream: None,
                                    topic_name: payload.topic_name,
                                    topic_type: payload.topic_type,
                                    certificate: certificate.clone(),
                                };
                                let _ = topic_operation_tx.send(topic_creator_request);
                            }
                            _ => {
                                warn!("unknown action {}", payload.ros_op);
                            }
                        }
                    }

                    _ => {
                        info!("operation {} not handled!", payload.api_op);
                    }
                }
            },
        }
    }
}
