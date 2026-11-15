protocol Finder {
    func find(_ value: String) -> String
}

class BaseService {
    func find(_ value: String) -> String {
        return value
    }
}

class UserService: BaseService, Finder {
    override func find(_ value: String) -> String {
        return normalize(value)
    }

    func normalize(_ value: String) -> String {
        return value
    }
}
