package demo.web

import demo.service.UserService
import org.springframework.security.access.prepost.PreAuthorize
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/users")
class UserController(private val users: UserService) {
    @GetMapping("/{id}")
    @PreAuthorize("hasRole('USER')")
    fun show(@PathVariable id: String): String {
        return users.find(id)
    }
}
