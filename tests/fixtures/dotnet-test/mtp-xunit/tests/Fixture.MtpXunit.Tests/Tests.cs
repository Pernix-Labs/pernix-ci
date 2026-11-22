using System;
using System.Threading.Tasks;
using DotNet.Testcontainers.Builders;
using Xunit;

namespace Fixture.MtpXunit.Tests;

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

public class ContainerTests
{
    [Fact]
    public async Task StartsAlpine()
    {
        await using var container = new ContainerBuilder("alpine:3.20")
            .WithCommand("sleep", "60")
            .Build();
        await container.StartAsync(TestContext.Current.CancellationToken);
        var result = await container.ExecAsync(["echo", "ok"], TestContext.Current.CancellationToken);
        Assert.Equal(0, result.ExitCode);
    }
}
