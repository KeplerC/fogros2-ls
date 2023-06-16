use crate::pipeline::construct_gdp_forward_from_bytes;
use crate::structs::get_gdp_name_from_topic;
use crate::structs::{GDPName, GDPPacket, GdpAction, Packet};
use futures::stream::StreamExt;

#[cfg(feature = "ros")]
use r2r::QosProfile;




use tokio::sync::mpsc::UnboundedReceiver;
use tokio::sync::mpsc::UnboundedSender;

#[cfg(feature = "ros")]
pub async fn ros_publisher(
    node_name: String, topic_name: String, topic_type: String, certificate: Vec<u8>,
    mut m_rx: UnboundedReceiver<GDPPacket>,
) {
    let node_gdp_name = GDPName(get_gdp_name_from_topic(
        &node_name,
        &topic_type,
        &certificate,
    ));
    info!("ROS {} takes gdp name {:?}", node_name, node_gdp_name);

    let topic_gdp_name = GDPName(get_gdp_name_from_topic(
        &topic_name,
        &topic_type,
        &certificate,
    ));
    info!("topic {} takes gdp name {:?}", topic_name, topic_gdp_name);

    let ctx = r2r::Context::create().expect("context creation failure");
    let mut node = r2r::Node::create(ctx, &node_name, "namespace").expect("node creation failure");
    let publisher = node
        .create_publisher_untyped(&topic_name, &topic_type, QosProfile::default())
        .expect("publisher creation failure");

    let _handle = tokio::task::spawn_blocking(move || loop {
        node.spin_once(std::time::Duration::from_millis(10));
        // std::thread::sleep(std::time::Duration::from_millis(100));
    });

    loop {
        tokio::select! {
            Some(pkt_to_forward) = m_rx.recv() => {
                if pkt_to_forward.action == GdpAction::Forward {
                    info!("new payload to publish ");
                    if pkt_to_forward.gdpname == topic_gdp_name {
                        let payload = pkt_to_forward.get_byte_payload().unwrap();
                        //let ros_msg = serde_json::from_str(str::from_utf8(payload).unwrap()).expect("json parsing failure");
                        // info!("the decoded payload to publish is {:?}", ros_msg);
                        publisher.publish(payload.clone()).unwrap();
                    } else{
                        info!("{:?} received a packet for name {:?}",pkt_to_forward.gdpname, topic_gdp_name);
                    }
                }
            },
        }
    }
}

#[cfg(feature = "ros")]
pub async fn ros_subscriber(
    node_name: String, topic_name: String, topic_type: String, certificate: Vec<u8>,
    m_tx: UnboundedSender<GDPPacket>,
) {
    let node_gdp_name = GDPName(get_gdp_name_from_topic(
        &node_name,
        &topic_type,
        &certificate,
    ));
    info!("ROS {} takes gdp name {:?}", node_name, node_gdp_name);

    let topic_gdp_name = GDPName(get_gdp_name_from_topic(
        &topic_name,
        &topic_type,
        &certificate,
    ));
    info!("topic {} takes gdp name {:?}", topic_name, topic_gdp_name);

    let ctx = r2r::Context::create().expect("context creation failure");
    let mut node = r2r::Node::create(ctx, &node_name, "namespace").expect("node creation failure");
    let mut subscriber = node
        .subscribe_untyped(&topic_name, &topic_type, QosProfile::default())
        .expect("topic subscribing failure");

    let _handle = tokio::task::spawn_blocking(move || loop {
        node.spin_once(std::time::Duration::from_millis(100));
    });

    loop {
        tokio::select! {
            Some(packet) = subscriber.next() => {
                info!("received a packet {:?}", packet);
                let ros_msg = packet;
                let packet = construct_gdp_forward_from_bytes(topic_gdp_name, node_gdp_name, ros_msg );
                m_tx.send(packet).expect("send for ros subscriber failure");

                // proc_gdp_packet(packet,  // packet
                //     &fib_tx,  //used to send packet to fib
                //     &channel_tx, // used to send GDPChannel to fib
                //     &m_tx, //the sending handle of this connection
                //     &rib_query_tx, // used to send GDPNameRecord to rib
                //     "".to_string(),
                // ).await;

            }
        }
    }
}
