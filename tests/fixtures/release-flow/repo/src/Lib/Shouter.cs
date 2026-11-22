using Fixture.Shared;

namespace Fixture.Lib;

public static class Shouter
{
    public static string Shout(string name) => Greeter.Greet(name).ToUpperInvariant();
}
