mod service;

use axum::{extract::Path, routing::get, Router};
use crate::service::{Finder, UserService};

async fn show_user(Path(id): Path<String>) -> String {
    let users = UserService::new();
    users.find(&id)
}

fn app() -> Router {
    Router::new().route("/users/:id", get(show_user)).layer(require_auth_layer())
}
