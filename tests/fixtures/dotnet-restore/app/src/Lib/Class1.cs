namespace Lib;

public static class Class1
{
    public static string Serialize(object value) => Newtonsoft.Json.JsonConvert.SerializeObject(value);
}
