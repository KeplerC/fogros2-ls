#[macro_use] extern crate log;

// sub crates and primitives
pub mod crypto;
pub mod network;
pub mod structs;

pub mod api_server;
pub mod rib;

// network processing
pub mod connection_fib;
pub mod db;
pub mod pipeline;
// util
pub mod commands;
pub mod topic_manager;
pub mod service_manager;
pub mod util;
use utils::error::Result;

pub fn start() -> Result<()> {
    // does nothing

    Ok(())
}
