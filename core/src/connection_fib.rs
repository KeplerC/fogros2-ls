
use crate::{
    structs::{GDPName, GDPPacket},
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tokio::sync::mpsc::{UnboundedReceiver, UnboundedSender};


#[derive(Debug, PartialEq, Eq, Clone, Copy, Serialize, Deserialize, Hash)]
pub enum FibChangeAction {
    ADD,
    PAUSE, // pausing the forwarding of the topic, keeping connections alive
    PAUSEADD, // adding the entry to FIB, but keeps it paused
    RESUME, // resume a paused topic
    DELETE, // deleting a local topic interface and all its connections 
}

#[derive(Debug, PartialEq, Eq, Clone, Copy, Serialize, Deserialize, Hash)]
pub enum TopicStateInFIB {
    RUNNING,
    PAUSED,
    DELETED,
}


#[derive(Debug)]
pub struct FibStateChange {
    pub action: FibChangeAction,
    pub topic_gdp_name: GDPName,
    pub forward_destination: Option<UnboundedSender<GDPPacket>>,
}

#[derive(Debug)]
pub struct FIBState {
    state: TopicStateInFIB,
    receivers: Vec<UnboundedSender<GDPPacket>>,
}


/// receive, check, and route GDP messages
///
/// receive from a pool of receiver connections (one per interface)
/// use a hash table to figure out the corresponding
///     hash table <gdp_name, send_tx>
///     TODO: use future if the destination is unknown
/// forward the packet to corresponding send_tx
pub async fn connection_fib_handler(
    mut fib_rx: UnboundedReceiver<GDPPacket>, // its tx used to transmit data to fib
    mut channel_rx: UnboundedReceiver<FibStateChange>, /* its tx used to update fib with new names/records */
) {
    let mut rib_state_table: HashMap<GDPName, FIBState> = HashMap::new();

    loop {
        tokio::select! {
            Some(pkt) = fib_rx.recv() => {
                info!("received GDP packet {}", pkt);
                let topic_state = rib_state_table.get(&pkt.gdpname);
                info!("the current topic state is {:?}", topic_state);
                match topic_state {
                    Some(s) => {
                        if s.state == TopicStateInFIB::RUNNING {
                            for dst in &s.receivers {
                                let _ = dst.send(pkt.clone());
                            }
                        } else {
                            warn!("the current topic state is {:?}, not forwarded", topic_state)
                        }
                    },
                    None => {
                        error!("The gdpname {:?} does not exist", pkt.gdpname)
                    }
                }
            }

            // update the table
            Some(update) = channel_rx.recv() => {
                match update.action {
                    FibChangeAction::ADD => {
                        info!("update status received {:?}", update);

                        match  rib_state_table.get_mut(&update.topic_gdp_name) {
                            Some(v) => {
                                v.state = TopicStateInFIB::RUNNING;
                                v.receivers.push(update.forward_destination.unwrap());
                            }
                            None =>{
                                info!("Creating a new entry of gdp name {:?}", update.topic_gdp_name);
                                let state = FIBState {
                                    state: TopicStateInFIB::RUNNING,
                                    receivers: vec!(update.forward_destination.unwrap()),
                                };
                                rib_state_table.insert(
                                    update.topic_gdp_name,
                                    state,
                                );
                            }
                        };
                        // TODO: pause add
                    },
                    FibChangeAction::PAUSEADD => {
                        //todo pause
                    },
                    FibChangeAction::PAUSE => {
                        info!("Pausing GDP Name {:?}", update.topic_gdp_name);
                        match  rib_state_table.get_mut(&update.topic_gdp_name) {
                            Some(v) => {
                                v.state = TopicStateInFIB::PAUSED;
                            }
                            None =>{
                                error!("pausing non existing state!");
                            }
                        };
                    },
                    FibChangeAction::RESUME => {
                        info!("Deleting GDP Name {:?}", update.topic_gdp_name);
                        match  rib_state_table.get_mut(&update.topic_gdp_name) {
                            Some(v) => {
                                v.state = TopicStateInFIB::RUNNING;
                            }
                            None =>{
                                error!("resuming non existing state!");
                            }
                        };
                    },
                    FibChangeAction::DELETE => {
                        info!("Deleting GDP Name {:?}", update.topic_gdp_name);
                        // rib_state_table.remove(&update.topic_gdp_name);
                        match  rib_state_table.get_mut(&update.topic_gdp_name) {
                            Some(v) => {
                                v.state = TopicStateInFIB::DELETED;
                            }
                            None =>{
                                error!("deleting non existing state!");
                            }
                        };
                    },
                }
            }
        }
    }
}


// async fn send_to_destination(destinations: Vec<GDPChannel>, packet: GDPPacket) {
//     for dst in destinations {
//         info!(
//             "data {} from {} send to {}",
//             packet.gdpname, packet.source, dst.source
//         );
//         if dst.source == packet.source {
//             info!("Equal to the source, skipped!");
//             continue;
//         }
//         let result = dst.channel.send(packet.clone());
//         match result {
//             Ok(_) => {}
//             Err(_) => {
//                 warn!("Send Failure: channel sent to destination is closed");
//             }
//         }
//     }
// }

// fn dump_fib_table(rib_table: &HashMap<GDPName, Vec<GDPChannel>>) {
//     info!("dumpping FIB table");
//     for (k, v) in rib_table {
//         for channel in v {
//             info!("{}, {},source: {}", k, channel.comment, channel.source);
//         }
//     }
// }


// pub async fn connection_fib(
//     mut fib_rx: UnboundedReceiver<GDPPacket>, rib_query_tx: UnboundedSender<GDPNameRecord>,
//     mut rib_response_rx: UnboundedReceiver<GDPNameRecord>,
//     mut stat_rs: UnboundedReceiver<GDPStatus>, mut channel_rx: UnboundedReceiver<GDPChannel>,
// ) {
//     // TODO: currently, we only take one rx due to select! limitation
//     // will use FutureUnordered Instead
//     let _receive_handle = tokio::spawn(async move {
//         let mut coonection_rib_table: HashMap<GDPName, Vec<GDPChannel>> = HashMap::new();
//         let mut counter = 0;

//         // loop polling from
//         loop {
//             tokio::select! {
//                 // GDP packet received
//                 // recv () -> find_where_to_route() -> route()
//                 Some(pkt) = fib_rx.recv() => {
//                     counter += 1;
//                     info!("RIB received the packet #{} with name {}", counter, &pkt.gdpname);

//                     // find where to route
//                     match coonection_rib_table.get(&pkt.gdpname) {
//                         Some(routing_dsts) => {
//                             send_to_destination(routing_dsts.clone(), pkt).await;
//                         }
//                         None => {
//                             warn!("{:} is not there, querying to RIB; in the meantime, packets are dropped", pkt.gdpname);
//                             rib_query_tx.send(
//                                 GDPNameRecord{
//                                     record_type: QUERY,
//                                     gdpname: pkt.gdpname,
//                                     source_gdpname: pkt.source,
//                                     webrtc_offer: None,
//                                     ip_address: None,
//                                     indirect: None,
//                                     ros:None,
//                                 }
//                             ).expect(
//                                 "failed to send RIB query response"
//                             );

//                             for routing_dsts in coonection_rib_table.values(){
//                                 send_to_destination(routing_dsts.clone(), pkt.clone()).await;
//                             }
//                         }
//                     }
//                 }

//                 // connection fib advertisement received
//                 Some(channel) = channel_rx.recv() => {
//                     info!("channel registry received {:?}", channel);

//                     match  coonection_rib_table.get_mut(&channel.gdpname) {
//                         Some(v) => {
//                             info!("adding to connectionfib vec");
//                             v.push(channel)
//                         }
//                         None =>{
//                             info!("Creating a new entry of gdp name");
//                             coonection_rib_table.insert(
//                                 channel.gdpname,
//                                 vec!(channel),
//                             );
//                         }
//                     };

//                 },

//                 // response from RIB
//                 Some(rib_response) = rib_response_rx.recv() => {
//                     info!("get RIB response {:?}", rib_response);
//                     match rib_response.record_type {
//                         // not found
//                         EMPTY => {
//                             warn!("Name {:?} is not registered in RIB, flooding the query...", rib_response.gdpname);
//                             for (channel_name, channel) in &coonection_rib_table {
//                                 info!("flushing advertisement for {} to {:?}", rib_response.gdpname, channel);
//                                 let packet = construct_rib_query_from_bytes(
//                                     rib_response.gdpname,
//                                     *channel_name,
//                                     GDPNameRecord{
//                                         record_type: QUERY,
//                                         gdpname: rib_response.gdpname,
//                                         source_gdpname: *channel_name, // so that one can send it back the the interface which issues the query
//                                         webrtc_offer: None,
//                                         ip_address: None,
//                                         indirect: None,
//                                         ros:None,
//                                     }
//                                 );

//                                 for dst in channel {
//                                     let result = dst.channel.send(packet.clone());
//                                     match result {
//                                         Ok(_) => {}
//                                         Err(_) => {
//                                             warn!("Send Failure: channel sent to destination is closed");
//                                         }
//                                     }
//                                 }
//                             }
//                         },
//                         INFO => {
//                             // get it back to the interface which issues the query
//                             let dst = rib_response.source_gdpname;
//                             info!("found the name {:?} in RIB, sending back to {:?}", rib_response.gdpname, dst);
//                             let pkt = construct_gdp_advertisement_from_structs(
//                                 rib_response.gdpname,
//                                 rib_response.source_gdpname,
//                                 rib_response
//                             );

//                             match coonection_rib_table.get(&dst) {
//                                 Some(routing_dsts) => {
//                                     for dst in routing_dsts {
//                                         dst.channel.send(pkt.clone()).expect("failed to send RIB query response");
//                                     }
//                                 }
//                                 None => {
//                                     dump_fib_table(&coonection_rib_table);
//                                     warn!("{:} is not there when sending the response of the RIB", dst);
//                                 }
//                             }

//                         }
//                         _ => {
//                             info!("rib response not handled!");
//                         }
//                     }
//                 },

//                 // TODO: update rib here, instead of fib
//                 Some(update) = stat_rs.recv() => {
//                     // Note: incomplete implementation, only support flushing advertisement
//                     let dst = update.sink;
//    