using Fixture.Lib;
using Xunit;

namespace Fixture.Lib.Tests;

public class ShouterTests
{
    [Fact]
    public void Shouts() => Assert.Equal("HELLO, LIB", Shouter.Shout("lib"));
}
