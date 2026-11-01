"""Pipeline steps. Each one is a module with main(argv); the job runner starts it as its own process
(atolye/calis.py), so a GPU step gives back all of its VRAM when it ends."""
ADIMLAR = ["sekil", "doku", "parcalar", "ayrik", "xpart", "toon", "piksel"]
