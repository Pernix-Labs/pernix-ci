using System;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[assembly: Parallelize(Scope = ExecutionScope.MethodLevel)]

namespace Fixture.MtpTrxReport.Tests;

[TestClass]
public class CalculatorTests
{
    [TestMethod]
    public void Adds() => Assert.AreEqual(4, Add(2, 2));

    [TestMethod]
    public void Subtracts() => Assert.AreEqual(0, Add(2, -2));

    private static int Add(int a, int b) => a + b;
}

[TestClass]
public class ForceFailTests
{
    [TestMethod]
    public void FailsOnlyWhenForced() =>
        Assert.AreNotEqual("1", Environment.GetEnvironmentVariable("FIXTURE_FORCE_FAIL"));
}
