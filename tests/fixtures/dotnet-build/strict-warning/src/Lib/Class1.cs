namespace Lib;

public static class Class1
{
    public static string Serialize(object value)
    {
        // CS0168: declared but never used. TreatWarningsAsErrors turns it into an error.
        int unused;
        return Newtonsoft.Json.JsonConvert.SerializeObject(value);
    }
}
