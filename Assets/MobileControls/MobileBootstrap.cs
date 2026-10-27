using UnityEngine;

namespace FPSSampleMobile
{
    // Cria o painel de controles sozinho ao carregar o jogo (não precisa mexer em cena).
    public static class MobileBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init()
        {
            if (Application.platform != RuntimePlatform.Android && Application.platform != RuntimePlatform.IPhonePlayer)
                return;
            if (Object.FindObjectOfType<MobileTouchControls>() != null) return;
            var go = new GameObject("MobileTouchControls");
            Object.DontDestroyOnLoad(go);
            go.AddComponent<MobileTouchControls>();
        }
    }
}
