use axum::{
    routing::{get}, Router,
};

use std::net::SocketAddr;

// basic handler that responds with a static string
async fn root() -> &'static str {
    "Hello, World!"
}

pub async fn ros_api_server() {

    // build our application with a route
    let app = Router::new()
        // `GET /` goes to `root`
        .route("/", get(root));

    // run our app with hyper
    // `axum::Server` is a re-export of `hyper::Server`
    let addr = SocketAddr::from(([127, 0, 0, 1], 3000));
    tracing::debug!("listening on {}", addr);
    axum::Server::bind(&addr)
        .serve(app.into_make_service())
        .await
        .unwrap();
}
