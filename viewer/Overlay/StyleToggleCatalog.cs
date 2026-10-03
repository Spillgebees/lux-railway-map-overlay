using System.Globalization;
using System.Text.Json;

namespace RailwayViewer.Overlay;

/// <summary>
/// Builds the viewer's toggle groups from style.json: each layer lists its toggle tokens in
/// <c>metadata.toggle</c>, and the root <c>metadata.toggleFamilies</c>, <c>toggleModes</c> and
/// <c>toggleStates</c> arrays give the token order per group.
/// </summary>
public static class StyleToggleCatalog
{
    private static readonly GroupDefinition[] _groups =
    [
        new("families", "Layers", "toggleFamilies", "family"),
        new("modes", "Modes", "toggleModes", "mode"),
        new("states", "Lifecycle", "toggleStates", "state"),
    ];

    private static readonly Dictionary<string, string> _labels = new(StringComparer.Ordinal)
    {
        ["stops"] = "Stations and stops",
        ["crossings"] = "Level crossings",
        ["areas"] = "Railway areas",
    };

    // The first drawn layer is the default legend sample; these tokens read better with another one.
    private static readonly Dictionary<string, string> _swatchLayers = new(StringComparer.Ordinal)
    {
        ["stops"] = "railway-stations-circle",
    };

    public static IReadOnlyList<ToggleGroup> Parse(JsonElement style)
    {
        var layers = style.TryGetProperty("layers", out var layersElement)
            ? layersElement.EnumerateArray().ToArray()
            : [];
        var rootMetadata = style.TryGetProperty("metadata", out var metadata) ? metadata : default;

        var groups = new List<ToggleGroup>();
        foreach (var group in _groups)
        {
            var tokens = ReadTokenOrder(rootMetadata, group, layers);
            var toggles = tokens.Select(token => BuildToggle(token, layers)).OfType<LayerToggle>().ToArray();

            if (toggles.Length > 0)
            {
                groups.Add(new ToggleGroup(group.Id, group.Title, toggles));
            }
        }

        return groups;
    }

    private static IReadOnlyList<string> ReadTokenOrder(
        JsonElement rootMetadata,
        GroupDefinition group,
        IEnumerable<JsonElement> layers
    )
    {
        if (
            rootMetadata.ValueKind == JsonValueKind.Object
            && rootMetadata.TryGetProperty(group.RootKey, out var order)
            && order.ValueKind == JsonValueKind.Array
        )
        {
            return [.. order.EnumerateArray().Select(token => token.GetString()).OfType<string>()];
        }

        // without a root list, fall back to the per-layer field in style order
        return
        [
            .. layers
                .Select(layer => LayerMetadataString(layer, group.LayerKey))
                .OfType<string>()
                .Distinct(StringComparer.Ordinal),
        ];
    }

    private static LayerToggle? BuildToggle(string token, IEnumerable<JsonElement> layers)
    {
        var matching = layers.Where(layer => LayerTokens(layer).Contains(token, StringComparer.Ordinal)).ToArray();
        if (matching.Length == 0)
        {
            return null;
        }

        var refs = matching.Select(layer => new StyleLayerRef(LayerId(layer), IsVisibleByDefault(layer))).ToArray();
        return new LayerToggle(token, LabelFor(token), SwatchFor(token, matching), refs);
    }

    private static string LabelFor(string token)
    {
        if (_labels.TryGetValue(token, out var label))
        {
            return label;
        }

        var words = token.Replace('_', ' ');
        return words.Length == 0 ? token : char.ToUpper(words[0], CultureInfo.InvariantCulture) + words[1..];
    }

    private static LegendSwatch? SwatchFor(string token, IReadOnlyList<JsonElement> layers)
    {
        if (_swatchLayers.TryGetValue(token, out var preferredId))
        {
            var preferred = layers.FirstOrDefault(layer => LayerId(layer) == preferredId);
            if (preferred.ValueKind == JsonValueKind.Object && ReadSwatch(preferred) is { } swatch)
            {
                return swatch;
            }
        }

        // prefer layers that are actually drawn by default, then anything with a usable paint
        return layers.Where(IsVisibleByDefault).Select(ReadSwatch).FirstOrDefault(swatch => swatch is not null)
            ?? layers.Select(ReadSwatch).FirstOrDefault(swatch => swatch is not null);
    }

    private static LegendSwatch? ReadSwatch(JsonElement layer)
    {
        if (!layer.TryGetProperty("paint", out var paint) || !layer.TryGetProperty("type", out var typeElement))
        {
            return null;
        }

        return typeElement.GetString() switch
        {
            "line" => ColorOf(paint, "line-color") is { } color
                ? new LegendSwatch(
                    SwatchKind.Line,
                    color,
                    null,
                    paint.TryGetProperty("line-dasharray", out _),
                    NumberOf(paint, "line-opacity")
                )
                : null,
            "fill" => ColorOf(paint, "fill-color") is { } color
                ? new LegendSwatch(
                    SwatchKind.Fill,
                    color,
                    ColorOf(paint, "fill-outline-color"),
                    false,
                    NumberOf(paint, "fill-opacity")
                )
                : null,
            "fill-extrusion" => ColorOf(paint, "fill-extrusion-color") is { } color
                ? new LegendSwatch(SwatchKind.Fill, color, null, false, NumberOf(paint, "fill-extrusion-opacity"))
                : null,
            "circle" => ColorOf(paint, "circle-color") is { } color
                ? new LegendSwatch(
                    SwatchKind.Circle,
                    color,
                    ColorOf(paint, "circle-stroke-color"),
                    false,
                    NumberOf(paint, "circle-opacity")
                )
                : null,
            _ => null,
        };
    }

    /// <summary>Reads a literal color, or the last literal color inside an expression (e.g. a coalesce fallback).</summary>
    private static string? ColorOf(JsonElement paint, string property)
    {
        return paint.TryGetProperty(property, out var value) ? LastColor(value) : null;

        static string? LastColor(JsonElement element) =>
            element.ValueKind switch
            {
                JsonValueKind.String when IsColor(element.GetString()) => element.GetString(),
                JsonValueKind.Array => element
                    .EnumerateArray()
                    .Reverse()
                    .Select(LastColor)
                    .FirstOrDefault(c => c is not null),
                _ => null,
            };

        // the value ends up in an inline style, so only accept plain color syntax
        static bool IsColor(string? value) =>
            value is not null
            && value.IndexOfAny([';', '{', '}', '"', '\'', '<', '>']) < 0
            && (
                value.StartsWith('#')
                || value.StartsWith("rgb", StringComparison.OrdinalIgnoreCase)
                || value.StartsWith("hsl", StringComparison.OrdinalIgnoreCase)
            );
    }

    private static double NumberOf(JsonElement paint, string property) =>
        paint.TryGetProperty(property, out var value) && value.ValueKind == JsonValueKind.Number
            ? value.GetDouble()
            : 1d;

    private static string LayerId(JsonElement layer) => layer.GetProperty("id").GetString() ?? string.Empty;

    private static bool IsVisibleByDefault(JsonElement layer) =>
        !(
            layer.TryGetProperty("layout", out var layout)
            && layout.TryGetProperty("visibility", out var visibility)
            && visibility.GetString() == "none"
        );

    private static IReadOnlyList<string> LayerTokens(JsonElement layer) =>
        layer.TryGetProperty("metadata", out var metadata)
        && metadata.ValueKind == JsonValueKind.Object
        && metadata.TryGetProperty("toggle", out var toggle)
        && toggle.ValueKind == JsonValueKind.Array
            ? [.. toggle.EnumerateArray().Select(token => token.GetString()).OfType<string>()]
            : [];

    private static string? LayerMetadataString(JsonElement layer, string key) =>
        layer.TryGetProperty("metadata", out var metadata)
        && metadata.ValueKind == JsonValueKind.Object
        && metadata.TryGetProperty(key, out var value)
        && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private sealed record GroupDefinition(string Id, string Title, string RootKey, string LayerKey);
}
