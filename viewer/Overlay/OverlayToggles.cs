namespace RailwayViewer.Overlay;

/// <summary>A section of related toggles, e.g. layer families or lifecycle states.</summary>
public sealed record ToggleGroup(string Id, string Title, IReadOnlyList<LayerToggle> Toggles);

/// <summary>One toggle token from style.json and the style layers that carry it.</summary>
public sealed record LayerToggle(string Token, string Label, LegendSwatch? Swatch, IReadOnlyList<StyleLayerRef> Layers)
{
    public IEnumerable<string> LayerIds => Layers.Select(layer => layer.Id);
}

/// <summary>A style layer, whether style.json ships it visible, and all of its toggle tokens.</summary>
public sealed record StyleLayerRef(string Id, bool VisibleByDefault, IReadOnlyList<string> Tokens);

public enum SwatchKind
{
    Line,
    Fill,
    Circle,
}

/// <summary>A small legend sample derived from a layer's paint properties.</summary>
public sealed record LegendSwatch(SwatchKind Kind, string Color, string? StrokeColor, bool Dashed, double Opacity);
