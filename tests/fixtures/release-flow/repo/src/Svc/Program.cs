using Fixture.Shared;

namespace Fixture.Svc;

public static class Program
{
    public static string Message(string[] args) => Greeter.Greet(args.Length > 0 ? args[0] : "svc");

    public static void Main(string[] args) => Console.WriteLine(Message(args));
}
