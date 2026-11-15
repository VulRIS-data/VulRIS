import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/api")
class Controller {
    @Autowired
    private Service service;

    Controller() {
        this.service = new Service();
    }

    @PreAuthorize("hasRole('USER')")
    @GetMapping("/items/{id}")
    String item(@PathVariable String id) {
        executeQuery(id);
        return service.find(id);
    }

    @Test
    void testItem() {
        item("1");
    }
}
