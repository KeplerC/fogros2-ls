use axum::extract::State;
use axum::{
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::sync::mpsc::UnboundedSender;

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
    tx: UnboundedSender<ROSTopicRequest>,
}


// basic handler that responds with a static string
async fn root() -> &'static str {
    "Hello, World!"
}

#[axum_macros::debug_handler]
// basic handler that responds with a static string
async fn handle_ros_topic(
    State(state): State<Arc<AppState>>, Json(payload): Json<ROSTopicRequest>,
) -> impl IntoResponse {
    info!("received {:?}", payload);
    state.tx.send(payload).expect("state sent failure");
    // insert your application logic here
    let result = ROSResponse {
        result: "done".to_owned(),
    };

    // this will be converted into a JSON response
    // with a status code of `201 Created`
    (StatusCode::CREATED, Json(result))
}


pub async fn ros_api_server(topic_request_tx: UnboundedSender<ROSTopicRequest>) {
    let app_state = Arc::new(AppState {
        tx: topic_request_tx,
    });
    // build our application with a route
    let app = Router::new()
        .route("/", get(root))
        .route("/topic", post(handle_ros_topic))
        .with_state(app_state);

    // run our app with hyper
    // `axum::Server` is a re-export of `hyper::Server`
    let addr = SocketAddr::from(([0, 0, 0, 0], 3000));
    tracing::debug!("listening on {}", addr);
    axum::Server::bind(&addr)
        .serve(app.into_make_service())
        .await
        .unwrap();
}
