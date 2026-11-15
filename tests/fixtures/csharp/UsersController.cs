using Demo.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Demo.Api;

[ApiController]
[Route("api/users")]
public class UsersController : ControllerBase
{
    private readonly UserService _users;

    public UsersController(UserService users)
    {
        _users = users;
    }

    [HttpGet("{id}")]
    [Authorize(Roles = "Admin")]
    public IActionResult Get([FromRoute] string id)
    {
        return Ok(_users.Find(id));
    }
}
