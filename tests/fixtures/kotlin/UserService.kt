package demo.service

open class BaseService {
    open fun find(value: String): String {
        return value
    }
}

class UserService : BaseService() {
    override fun find(value: String): String {
        return value.trim()
    }
}
