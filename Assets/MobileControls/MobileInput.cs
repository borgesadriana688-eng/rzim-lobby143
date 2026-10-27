using System.Collections.Generic;
using UnityEngine;

namespace FPSSampleMobile
{
    // Fonte central de input mobile. O Game.cs do FPSSample consulta esta classe
    // antes do Input clássico (veja Patches/apply_patch.py).
    public static class MobileInput
    {
        static readonly Dictionary<string, float> axes = new Dictionary<string, float>();
        static readonly HashSet<KeyCode> keys = new HashSet<KeyCode>();
        static readonly HashSet<KeyCode> keysDown = new HashSet<KeyCode>();
        static readonly HashSet<int> mouse = new HashSet<int>();

        public static void SetAxis(string axis, float value) { axes[axis] = value; }
        public static void ClearAxis(string axis) { if (axes.ContainsKey(axis)) axes[axis] = 0f; }

        public static void SetKey(KeyCode k, bool down)
        {
            if (down) { if (!keys.Contains(k)) keysDown.Add(k); keys.Add(k); }
            else keys.Remove(k);
        }
        public static void SetMouse(int button, bool down)
        {
            if (down) mouse.Add(button); else mouse.Remove(button);
        }
        public static void ClearFrameEdge() { keysDown.Clear(); }

        public static float GetAxisRaw(string axis)
        {
            float v;
            return axes.TryGetValue(axis, out v) ? v : 0f;
        }
        public static bool GetKey(KeyCode k) { return keys.Contains(k); }
        public static bool GetKeyDown(KeyCode k) { return keysDown.Contains(k); }
        public static bool GetKeyUp(KeyCode k) { return false; }
        public static bool GetMouseButton(int b) { return mouse.Contains(b); }
    }
}
