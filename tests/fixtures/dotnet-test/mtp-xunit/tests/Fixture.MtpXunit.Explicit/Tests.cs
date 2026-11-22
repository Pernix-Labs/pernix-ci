using Xunit;

namespace Fixture.MtpXunit.Explicit;

// Runs only when requested explicitly. A default run discovers zero tests
// here, which the block tolerates per project.
public class ExplicitOnlyTests
{
    [Fact(Explicit = true)]
    public void RunsOnlyOnRequest() => Assert.True(true);
}
