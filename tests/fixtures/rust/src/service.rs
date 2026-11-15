pub trait Finder {
    fn find(&self, value: &str) -> String;
}

pub struct UserService;

impl UserService {
    pub fn new() -> Self {
        UserService
    }
}

impl Finder for UserService {
    fn find(&self, value: &str) -> String {
        value.trim().to_string()
    }
}
