use utils::app_config::*;

#[test]
fn verify_get() {
    // Initialize configuration
    let config_contents = include_str!("resources/test_config.toml");
    AppConfig::init(Some(config_contents)).unwrap();

    // Check value with get
    assert_eq!(AppConfig::get::<bool>("debug").unwrap(), false);
}

#[test]
fn verify_set() {
    // Initialize configuration
    let config_contents = include_str!("resources/test_config.toml");
    AppConfig::init(Some(config_contents)).unwrap();

    // Set a field
    AppConfig::set("database.url", "new url").unwrap();

    // Fetch a new instance of Config
    let _config = AppConfig::fetch().unwrap();
}
