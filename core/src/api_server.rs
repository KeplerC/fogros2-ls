use axum::{
    routing::{get, post},
    http::StatusCode,
    response::IntoResponse,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;



#[derive(Debug, Serialize, Deserialize)]
pub struct ROSTopicRequest {
    pub api_op: String, // add | del 
    pub ros_op: String, // pub | sub | noop
    pub crypto: String, 
    pub topic_name: String,
    pub topic_type: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ROSResponse {
    pub result: String,
}

// Our shared state
struct AppState {
    // Channel used to send messages to all connected clients.
    tx: UnboundedSender<ROSTopic>, 
}


// basic handler that responds with a static string
async fn root() -> &'static str {
    "Hello, World!"
}

// basic handler that responds with a static string
async fn handle_ros_topic(
    // this argument tells axum to parse the request body
    // as JSON into a `CreateUser` type
    Json(payload): Json<ROSTopic>,
    State(state): State<Arc<AppState>>,
) -> (StatusCode, Json<ROSResponse>) {
    info!("received {:?}", payload);
    state.tx.send(payload);
    // insert your application logic here
    let result = ROSResponse {
        result: "done".to_owned(),
    };

    // this will be converted into a JSON response
    // with a status code of `201 Created`
    (StatusCode::CREATED, Json(result))
}


pub async fn ros_api_server(
    topic_request_tx: UnboundedSender<ROSTopic>, 
) {

    let app_state = Arc::new(AppState { tx: topic_request_tx });
    // build our application with a route
    let app = Router::new()
        .route("/", get(root))
        .route("/add", post(handle_ros_topic))
        .with_state(app_state);

    // run our app with hyper
    // `axum::Server` is a re-export of `hyper::Server`
    let addr = SocketAddr::from(([127, 0, 0, 1], 3000));
    tracing::debug!("listening on {}", addr);
    axum::Server::bind(&addr)
        .serve(app.into_make_service())
        .await
        .unwrap();
}
