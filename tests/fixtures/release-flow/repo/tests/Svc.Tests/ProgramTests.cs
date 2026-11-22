using Fixture.Svc;
using Xunit;

namespace Fixture.Svc.Tests;

public class ProgramTests
{
    [Fact]
    public void DefaultMessage() => Assert.Equal("hello, svc", Program.Message([]));
}
