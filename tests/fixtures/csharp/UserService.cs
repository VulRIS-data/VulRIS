namespace Demo.Services;

public interface IFinder
{
    string Find(string value);
}

public class UserService : IFinder
{
    public string Find(string value) => value.Trim();
}
