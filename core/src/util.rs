use std::env;

// read from environment variable signaling server address
pub fn get_signaling_server_address() -> String{
    match env::var_os("SGC_SIGNAL_SERVER_ADDRESS") {
        Some(address) => {
            address.into_string().unwrap()
        }
        None => {
            info!("Using default signaling server address");
            "ws://3.18.194.127:8000".to_owned()
        }
    }
}

// read from environment variable rib address
pub fn get_rib_server_address() -> String{
    match env::var_os("SGC_RIB_SERVER_ADDRESS") {
        Some(address) => {
            address.into_string().unwrap()
        }
        None => {
            info!("Using default rib server address");
            "3.18.194.127:8002".to_owned()
        }
    }
}