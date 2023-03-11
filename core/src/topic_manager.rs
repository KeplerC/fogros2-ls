use std::collections::HashMap;
use tokio::time::sleep;
use tokio::time::Duration;
use futures::future;
use futures::executor::LocalPool;
use r2r::QosProfile;
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc::{self, UnboundedSender};
use utils::app_config::AppConfig;
use crate::network::dtls::{dtls_listener, dtls_test_client, dtls_to_peer, dtls_to_peer_direct};
#[cfg(feature = "ros")]
use crate::network::ros::{ros_publisher, ros_subscriber};
#[cfg(feature = "ros")]
use crate::network::ros::{ros_publisher_image, ros_subscriber_image};
use crate::network::tcp::tcp_to_peer_direct;
use crate::structs::{GDPPacket, GDPChannel};
use futures::stream::{self, StreamExt};
// use r2r::Node::get_topic_names_and_types;

/// function that creates a new thread for each topic 
/// and spawns a new thread that peers with the gateway
pub async fn topic_creator(
    peer_with_gateway: bool, 
    default_gateway_addr: String, 
    node_name: String,
    protocol : String,
    topic_name: String,
    topic_type: String,
    publish_or_subscribe: String, 
    rib_tx: UnboundedSender<GDPPacket>, 
    channel_tx: UnboundedSender<GDPChannel>,
){
    if publish_or_subscribe == "noop" {
        info!("noop for topic {}", topic_name);
        return;
    }

    // This sender handle is a specific connection for ROS
    // this is used to diffentiate different channels in ROS topics
    let (mut m_tx, m_rx) = mpsc::unbounded_channel();
    if  peer_with_gateway {
        if protocol == "dtls" {
            let _ros_peer = tokio::spawn(dtls_to_peer_direct(
                default_gateway_addr.clone().into(),
                rib_tx.clone(),
                channel_tx.clone(),
                m_tx.clone(),
                m_rx,
            ));
        } else if protocol == "tcp" {
            let _ros_peer = tokio::spawn(tcp_to_peer_direct(
                default_gateway_addr.clone().into(),
                rib_tx.clone(),
                channel_tx.clone(),
                m_tx.clone(),
                m_rx,
            ));
        }
    } else {
        // reasoning here:
        // m_tx is the next hop that the ros sends messages
        // if we don't peer with another router directly
        // we just forward to rib
        m_tx = rib_tx.clone();
    }

    let _ros_handle = match publish_or_subscribe.as_str() {
        "pub" => match topic_type.as_str() {
            "sensor_msgs/msg/CompressedImage" => tokio::spawn(ros_subscriber_image(
                m_tx.clone(),
                channel_tx.clone(),
                node_name,
                topic_name,
            )),
            _ => tokio::spawn(ros_subscriber(
                m_tx.clone(),
                channel_tx.clone(),
                node_name,
                topic_name,
                topic_type,
            )),
        },
        "sub" => match topic_type.as_str() {
            "sensor_msgs/msg/CompressedImage" => tokio::spawn(ros_publisher_image(
                m_tx.clone(),
                channel_tx.clone(),
                node_name,
                topic_name,
            )),
            _ => tokio::spawn(ros_publisher(
                m_tx.clone(),
                channel_tx.clone(),
                node_name,
                topic_name,
                topic_type,
            )),
        },
        _ => panic!("unknown action"),
    };

}

/// determine the action of a new topic 
/// pub/sub/noop
/// TODO: this is a temporary placeholder
async fn determine_topic_action(topic_name: String) -> String {
    "noop".to_string()
}

#[derive(Debug, PartialEq, Serialize, Deserialize, Clone)]
pub struct RosTopicStatus {
    pub action: String,
}

pub async fn ros_topic_manager(
    peer_with_gateway:bool, 
    default_gateway_addr:String, 
    rib_tx: UnboundedSender<GDPPacket>, 
    channel_tx: UnboundedSender<GDPChannel>,
){
    // get ros information from config file
    let config = AppConfig::fetch().expect("Failed to fetch config");
    // bookkeeping the status of ros topics
    let mut topic_status = HashMap::new();


    for topic in config.ros {
        let node_name = topic.node_name;
        let protocol = topic.protocol;
        let topic_name = topic.topic_name;
        let topic_type = topic.topic_type;
        let action = topic.local;
        topic_creator(
            peer_with_gateway, 
            default_gateway_addr.clone(), 
            node_name,
            protocol,
            topic_name.clone(),
            topic_type,
            action.clone(), 
            rib_tx.clone(), 
            channel_tx.clone(),
        ).await;

        topic_status.insert(topic_name, RosTopicStatus{action:action.clone()});
    }

    let ctx = r2r::Context::create().expect("failed to create context");
    let node = r2r::Node::create(ctx, "ros_manager", "namespace").expect("failed to create node");
    // when a new topic is detected, create a new thread 
    // to handle the topic
    loop {
        let current_topics = node.get_topic_names_and_types().unwrap();
        // check if there is a new topic by comparing current topics with 
        // the bookkeeping topics
        for topic in current_topics {
            if !topic_status.contains_key(&topic.0) {
                let topic_name = topic.0.clone();
                let action = determine_topic_action(topic_name.clone()).await;
                info!("detect a new topic {:?}", topic);
                topic_creator(
                    peer_with_gateway, 
                    default_gateway_addr.clone(), 
                    format!("{}_{}", "ros_manager", topic.0),
                    config.ros_protocol.clone(),
                    topic_name.clone(),
                    topic.1[0].clone(),
                    action.clone(), 
                    rib_tx.clone(), 
                    channel_tx.clone(),
                ).await;
                topic_status.insert(topic_name.clone(), 
                        RosTopicStatus{action:action});
            } else {
                info!("automatic new topic checker: topic already exists {:?}", topic);
            }
        }
        sleep(Duration::from_millis(2000)).await;
    }

    // TODO: a better way to detect new ros topic is needed
    // the following is an intuition that doesn't work
    // we subscribe to /parameter_events, whenever a new node joins
    // it will publish some message to this topic, but it doesn't have 
    // the topic information, so we run a topic detection 
    // let mut param_subscriber = node.
    // subscribe_untyped("/parameter_events", "rcl_interfaces/msg/ParameterEvent", QosProfile::default())
    // .expect("subscribe failed");
    // loop {
    //     info!("in the loop!");
    //     tokio::select! {
    //         Some(packet) = param_subscriber.next() => {
    //             info!("detect a new node {:?}", packet);
    //             
    //         }
    //     }
    // }
}
