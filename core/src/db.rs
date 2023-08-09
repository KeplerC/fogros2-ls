use redis::{self, Client, Commands, RedisResult};


use utils::app_config::AppConfig;
const routing_information_base_address:&str =  "3.18.194.127:8002";


pub fn get_redis_url() -> String {
    // let config = AppConfig::fetch().expect("Failed to fetch config");
    format!("redis://{}", routing_information_base_address)
}

pub fn get_redis_address_and_port() -> (String, u16) {
    let config = AppConfig::fetch().expect("Failed to fetch config");
    let url = config.routing_information_base_address;
    let mut split = url.split(":");
    let address = split.next().unwrap().to_string();
    let port = split.next().unwrap().parse::<u16>().unwrap();
    (address, port)
}

pub fn clear_topic_key(topic: &str) {
    let (address, port) = get_redis_address_and_port();
    let client = redis::Client::open(format!("redis://{}:{}", address, port)).unwrap();
    let mut con = client.get_connection().unwrap();
    let publisher_topic = format!("{}-pub", topic);
    let subscriber_topic = format!("{}-sub", topic);

    redis::cmd("DEL").arg(publisher_topic).execute(&mut con);
    redis::cmd("DEL").arg(subscriber_topic).execute(&mut con);
}

// add a publisher/subscriber to the database
pub fn add_entity_to_database_as_transaction(
    redis_url: &str, key: &str, value: &str,
) -> RedisResult<()> {
    let client = Client::open(redis_url)?;
    let mut con = client.get_connection()?;
    let (new_val,): (isize,) = redis::transaction(&mut con, &[key], |con, pipe| {
        pipe.lpush(key, value).query(con)
    })?;
    info!("The current number of entities in database is: {}", new_val);
    println!("successfully added entity {} {} to database {}", key, value, new_val);
    Ok(())
}

// get list of publishers/subscribers from the database
pub fn get_entity_from_database(redis_url: &str, key: &str) -> RedisResult<Vec<String>> {
    let client = Client::open(redis_url)?;
    let mut con = client.get_connection()?;
    let list: Vec<String> = con.lrange(key, 0, -1)?;
    Ok(list)
}

pub fn allow_keyspace_notification(redis_url: &str) -> RedisResult<()> {
    let client = Client::open(redis_url)?;
    let mut con = client.get_connection()?;
    let _: () = redis::cmd("CONFIG")
        .arg("SET")
        .arg("notify-keyspace-events")
        .arg("KEA")
        .query(&mut con)
        .expect("failed to execute SET for notify-keyspace-events");

    Ok(())
}
