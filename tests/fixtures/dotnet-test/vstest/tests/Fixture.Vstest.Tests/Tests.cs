using System;
using Xunit;

namespace Fixture.Vstest.Tests;

public class CalculatorTests
{
    [Fact]
    public void Adds() => Assert.Equal(4, 2 + 2);

    [Fact]
    public void Subtracts() => Assert.Equal(0, 2 - 2);
}

public class ForceFailTests
{
    [Fact]
    public void FailsOnlyWhenForced() =>
        Assert.NotEqual("1", Environment.GetEnvironmentVariable("FIXTURE_FORCE_FAIL"));
}
