using UnityEditor;
using UnityEngine;

[CustomEditor(typeof(SpriteSheetImporter))]
public class SpriteSheetImporterEditor : Editor
{
    public override void OnInspectorGUI()
    {
        DrawDefaultInspector();
        var importer = (SpriteSheetImporter)target;
        EditorGUILayout.Space();
        if (!GUILayout.Button("Import Sheet From JSON"))
        {
            return;
        }

        if (importer.SheetTexture == null)
        {
            Debug.LogError("SpriteSheetImporter: assign sheetTexture.");
            return;
        }

        string texPath = AssetDatabase.GetAssetPath(importer.SheetTexture);
        string outFolder = string.IsNullOrWhiteSpace(importer.OutputFolder)
            ? null
            : importer.OutputFolder.TrimEnd('/', '\\') + "/" +
              System.IO.Path.GetFileNameWithoutExtension(texPath).Replace("_sheet", "");

        try
        {
            var result = FrameforgeSheetImport.ImportAtPath(texPath, outFolder);
            Debug.Log($"SpriteSheetImporter: imported {result.CharacterName} into {result.OutputFolder}");
        }
        catch (System.Exception ex)
        {
            Debug.LogError($"SpriteSheetImporter: {ex.Message}");
        }
    }
}
