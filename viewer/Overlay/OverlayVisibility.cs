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

    /// <summary>Tokens of toggles that are disabled because none of their layers can be shown.</summary>
    public static IReadOnlySet<string> UnavailableTokens(IEnumerable<ToggleGroup> groups) =>
        groups
            .SelectMany(group => group.Toggles)
            .Where(toggle => !IsAvailable(toggle))
            .Select(toggle => toggle.Token)
            .ToHashSet(StringComparer.Ordinal);

    /// <summary>
    /// Whether most of an available toggle's layers stay hidden for reasons the panel doesn't already
    /// show. Layers that also carry a disabled token (e.g. tram construction under "Construction")
    /// are explained by that disabled toggle and don't count.
    /// </summary>
    public static bool IsMostlyUnreachable(LayerToggle toggle, IReadOnlySet<string> unavailableTokens)
    {
        var unexplained = toggle.Layers.Count(layer =>
            !CanRevealStyleHiddenLayers && !layer.VisibleByDefault && !layer.Tokens.Any(unavailableTokens.Contains)
        );
        return unexplained * 2 > toggle.Layers.Count;
    }

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
