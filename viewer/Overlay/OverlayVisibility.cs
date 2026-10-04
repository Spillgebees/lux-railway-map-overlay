using Spillgebees.Blazor.Map;

namespace RailwayViewer.Overlay;

/// <summary>
/// Maps toggles onto <see cref="MapDisplayState" /> items. Each toggle becomes one display item that
/// targets every style layer carrying its token. An item that is on shows its layers, even ones
/// style.json hides, and an item that is off hides them, so a layer draws only when its family, mode
/// and lifecycle toggles are all on.
/// </summary>
public static class OverlayVisibility
{
    /// <summary>A toggle starts on when style.json draws at least one of its layers.</summary>
    public static bool StartsOn(LayerToggle toggle) => toggle.Layers.Any(layer => layer.VisibleByDefault);

    public static IEnumerable<MapDisplayItem> ToDisplayItems(string styleId, IEnumerable<ToggleGroup> groups) =>
        groups
            .SelectMany(group => group.Toggles)
            .Select(toggle => new MapDisplayItem(
                toggle.Token,
                [MapDisplayTarget.StyleLayers(styleId, [.. toggle.LayerIds])],
                IsOn: StartsOn(toggle),
                Label: toggle.Label
            ));
}
