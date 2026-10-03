using Spillgebees.Blazor.Map;

namespace RailwayViewer.Overlay;

/// <summary>
/// Maps toggles onto <see cref="MapDisplayState" /> items. Each toggle becomes one display item that
/// targets every style layer carrying its token. The display engine hides a layer when any item
/// containing it is off, so a layer draws only when its family, mode and lifecycle toggles are all on.
/// </summary>
public static class OverlayVisibility
{
    /// <summary>
    /// Spillgebees.Blazor.Map 0.23.0 computes visibility as "style.json visibility AND every display
    /// item" (src/Spillgebees.Blazor.Map.Assets/src/engine/visibility.ts). Layers that style.json ships
    /// with <c>layout.visibility: "none"</c> (tram, crossings, most infrastructure) can be hidden but
    /// never revealed. Set this to true once the library can reveal them; toggles then stop being
    /// disabled and the "hidden by the style" hints disappear.
    /// </summary>
    public static bool CanRevealStyleHiddenLayers => false;

    /// <summary>Whether switching the toggle on can make anything appear on the map.</summary>
    public static bool IsAvailable(LayerToggle toggle) =>
        CanRevealStyleHiddenLayers || toggle.Layers.Any(layer => layer.VisibleByDefault);

    /// <summary>Layers of the toggle that stay hidden because style.json hides them.</summary>
    public static int UnreachableLayerCount(LayerToggle toggle) =>
        CanRevealStyleHiddenLayers ? 0 : toggle.Layers.Count(layer => !layer.VisibleByDefault);

    /// <summary>
    /// Initial state mirrors style.json: a toggle starts on when the style draws at least one of its
    /// layers, so the panel never shows a toggle as on while none of its layers is drawn.
    /// </summary>
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
