using UnityEngine;

/// <summary>
/// Optional inspector hook for Frameforge sheets.
/// Prefer: select *_sheet.png → Assets → Frameforge → Import Selected Sheet.
/// Auto-import also runs when a *_sheet.png + sibling JSON lands under Assets/.
/// Assign references in the inspector — do not use GameObject.Find.
/// </summary>
public class SpriteSheetImporter : MonoBehaviour
{
    [SerializeField] Texture2D sheetTexture;
    [SerializeField] TextAsset sheetJson;
    [SerializeField] string outputFolder = "Assets/Creatures/spritesheets";

    public Texture2D SheetTexture => sheetTexture;
    public TextAsset SheetJson => sheetJson;
    public string OutputFolder => outputFolder;
}
