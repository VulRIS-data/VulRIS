import Foundation

func showUser(_ id: String) -> String {
    let users = UserService()
    let task = Process()
    try? task.run()
    return users.find(id)
}
