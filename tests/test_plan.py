from atolye.isler import GirdiHatasi, ayarlari_dogrula, plan

SIS = {"gpu": {"toplam_gb": 31.84}, "blender": True, "modeller": {"xpart": True}}


def durumlar(p):
    return {a: (s["durum"], s.get("neden")) for a, s in p.items() if s["durum"] == "atlandi"}


def test_hafif_ve_parcali():
    assert durumlar(plan(ayarlari_dogrula({}), SIS)) == {
        "parcalar": ("atlandi", "rota"), "ayrik": ("atlandi", "rota"), "xpart": ("atlandi", "rota")}
    # X-Part runs on any card (Windows spills below its need); only a missing model skips it
    p = plan(ayarlari_dogrula({"rota": "parcali", "xpart": "1"}), SIS)
    assert durumlar(p) == {}
    p = plan(ayarlari_dogrula({"rota": "parcali", "xpart": "1"}), {**SIS, "modeller": {"xpart": False}})
    assert durumlar(p) == {"xpart": ("atlandi", "model_yok")}


def test_blender_yok_ve_doku_kapali():
    p = plan(ayarlari_dogrula({"doku": "false"}), {**SIS, "blender": False})
    d = durumlar(p)
    assert d["toon"] == ("atlandi", "blender_yok") and d["piksel"] == ("atlandi", "blender_yok")
    assert d["doku"] == ("atlandi", "secilmedi") and p["sekil"]["durum"] == "bekliyor"


def test_ayar_dogrulama():
    a = ayarlari_dogrula({"birlestir": "on", "parca_tohum": "7", "piksel_boy": "96"})
    assert a["birlestir"] is True and a["parca_tohum"] == 7 and a["piksel_boy"] == 96
    for kotu in ({"parca_tohum": "x"}, {"toon_aci": "arka"}, {"palet": "../x"}, {"piksel_boy": "8"}):
        try:
            ayarlari_dogrula(kotu)
        except GirdiHatasi:
            continue
        raise AssertionError(kotu)
