using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;

namespace FPSSampleMobile
{
    // Joystick esquerdo = movimento | Arrastar na metade direita = olhar
    // Botões: FIRE, JUMP, CROUCH, SPRINT, RELOAD, ARMA, MIRA
    public class MobileTouchControls : MonoBehaviour
    {
        // Ajuste aqui os códigos se o build do FPSSample usar outros binds
        public KeyCode jumpKey = KeyCode.Space;
        public KeyCode crouchKey = KeyCode.C;
        public KeyCode sprintKey = KeyCode.LeftShift;
        public KeyCode reloadKey = KeyCode.R;
        public KeyCode weaponKey = KeyCode.Q;

        public float joystickRadius = 110f;
        public float lookSensitivity = 2.2f;

        RectTransform stickBase, stickKnob;
        int moveFinger = -1, lookFinger = -1;
        Vector2 stickCenter, lookLast;
        Canvas canvas;

        void Start()
        {
            BuildUI();
        }

        void BuildUI()
        {
            canvas = gameObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = gameObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920, 1080);
            gameObject.AddComponent<GraphicRaycaster>();
            if (FindObjectOfType<EventSystem>() == null)
            {
                var es = new GameObject("EventSystem");
                es.AddComponent<EventSystem>();
                es.AddComponent<StandaloneInputModule>();
            }

            stickBase = MakeImage("StickBase", new Color(1, 1, 1, 0.18f), 220, 220);
            stickBase.anchorMin = stickBase.anchorMax = new Vector2(0, 0);
            stickBase.pivot = new Vector2(0.5f, 0.5f);
            stickBase.anchoredPosition = new Vector2(230, 260);
            stickKnob = MakeImage("StickKnob", new Color(1, 1, 1, 0.45f), 96, 96);
            stickKnob.SetParent(stickBase, false);
            stickKnob.anchoredPosition = Vector2.zero;
            stickCenter = stickBase.anchoredPosition;

            MakeButton("FIRE", new Vector2(-230, 300), 190, () => Toggle("fire", true), () => Toggle("fire", false));
            MakeButton("JUMP", new Vector2(-200, 520), 120, () => Press(jumpKey), () => Release(jumpKey));
            MakeButton("MIRA", new Vector2(-470, 300), 110, () => Toggle("aim", true), () => Toggle("aim", false));
            MakeButton("ATIRAR2", new Vector2(-390, 130), 110, () => Press(reloadKey), () => Release(reloadKey));
            MakeButton("CROUCH", new Vector2(-120, 130), 110, () => Toggle("crouch", true), () => Toggle("crouch", false));
            MakeButton("ARMA", new Vector2(-350, 500), 100, () => Press(weaponKey), () => Release(weaponKey));
            MakeButton("SPRINT", new Vector2(-560, 130), 100, () => Toggle("sprint", true), () => Toggle("sprint", false));
        }

        void Toggle(string what, bool on)
        {
            switch (what)
            {
                case "fire": MobileInput.SetAxis("Trigger", on ? -1f : 0f); MobileInput.SetMouse(0, on); break;
                case "aim": MobileInput.SetMouse(1, on); break;
                case "crouch": MobileInput.SetKey(crouchKey, on); break;
                case "sprint": MobileInput.SetKey(sprintKey, on); break;
            }
        }
        void Press(KeyCode k) { MobileInput.SetKey(k, true); }
        void Release(KeyCode k) { MobileInput.SetKey(k, false); }

        RectTransform MakeImage(string name, Color c, float w, float h)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(transform, false);
            var img = go.GetComponent<Image>();
            img.color = c;
            var rt = go.GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(w, h);
            return rt;
        }

        void MakeButton(string label, Vector2 pos, float size, System.Action down, System.Action up)
        {
            var rt = MakeImage("Btn" + label, new Color(1, 1, 1, 0.25f), size, size);
            rt.anchorMin = rt.anchorMax = new Vector2(1, 0);
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.anchoredPosition = pos;
            var txt = new GameObject("Txt", typeof(RectTransform), typeof(Text));
            txt.transform.SetParent(rt, false);
            var t = txt.GetComponent<Text>();
            t.text = label; t.alignment = TextAnchor.MiddleCenter; t.fontSize = 26;
            t.color = Color.white;
            t.font = Resources.GetBuiltinResource<Font>("Arial.ttf");
            var trt = txt.GetComponent<RectTransform>();
            trt.anchorMin = Vector2.zero; trt.anchorMax = Vector2.one; trt.offsetMin = trt.offsetMax = Vector2.zero;
            var trig = rt.gameObject.AddComponent<TouchButtonTrigger>();
            trig.onDown = down; trig.onUp = up;
        }

        void Update()
        {
            MobileInput.ClearFrameEdge();
            for (int i = 0; i < Input.touchCount; i++)
            {
                var t = Input.GetTouch(i);
                bool left = t.position.x < Screen.width * 0.5f;
                if (t.phase == TouchPhase.Began)
                {
                    if (left && moveFinger < 0 && Vector2.Distance(t.position, stickCenter) < joystickRadius * 2f)
                        moveFinger = t.fingerId;
                    else if (!left && lookFinger < 0 && lookFinger != moveFinger)
                        lookFinger = t.fingerId;
                    if (t.fingerId == lookFinger) lookLast = t.position;
                }
                else if (t.phase == TouchPhase.Moved || t.phase == TouchPhase.Stationary)
                {
                    if (t.fingerId == moveFinger)
                    {
                        Vector2 d = t.position - stickCenter;
                        if (d.magnitude > joystickRadius) d = d.normalized * joystickRadius;
                        stickKnob.anchoredPosition = d;
                        MobileInput.SetAxis("Horizontal", d.x / joystickRadius);
                        MobileInput.SetAxis("Vertical", d.y / joystickRadius);
                    }
                    else if (t.fingerId == lookFinger)
                    {
                        Vector2 delta = t.position - lookLast;
                        lookLast = t.position;
                        MobileInput.SetAxis("Mouse X", delta.x * lookSensitivity);
                        MobileInput.SetAxis("Mouse Y", delta.y * lookSensitivity);
                    }
                }
                else if (t.phase == TouchPhase.Ended || t.phase == TouchPhase.Canceled)
                {
                    if (t.fingerId == moveFinger)
                    {
                        moveFinger = -1; stickKnob.anchoredPosition = Vector2.zero;
                        MobileInput.SetAxis("Horizontal", 0); MobileInput.SetAxis("Vertical", 0);
                    }
                    if (t.fingerId == lookFinger)
                    {
                        lookFinger = -1;
                        MobileInput.SetAxis("Mouse X", 0); MobileInput.SetAxis("Mouse Y", 0);
                    }
                }
            }
        }
    }

    // Captura toque no botão (uGUI Button precisa de EventSystem; este é mais simples)
    public class TouchButtonTrigger : MonoBehaviour, IPointerDownHandler, IPointerUpHandler
    {
        public System.Action onDown, onUp;
        public void OnPointerDown(PointerEventData e) { if (onDown != null) onDown(); }
        public void OnPointerUp(PointerEventData e) { if (onUp != null) onUp(); }
    }
}
