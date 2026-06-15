"""
Tests de límites de recursos y configuración del contenedor Docker.

Qué verifica:
  - CPU limitada a 1 core (cpu_quota / cpu_period = 1.0)
  - Memoria limitada a 1 GB
  - Sin swap extra (MemorySwap == Memory)
  - El volumen /data está montado como solo lectura (mode: ro)

Estado esperado ANTES de implementar: todos fallan (sin límites configurados).
Estado esperado DESPUÉS de implementar: todos pasan.
"""


ONE_GB = 1 * 1024 ** 3  # 1 073 741 824 bytes


def test_contenedor_tiene_limite_cpu(singleuser_container):
    host_cfg = singleuser_container.attrs["HostConfig"]
    assert host_cfg.get("CpuPeriod") == 100_000, (
        f"CpuPeriod debe ser 100_000 µs, se obtuvo: {host_cfg.get('CpuPeriod')}"
    )
    assert host_cfg.get("CpuQuota") == 100_000, (
        "CpuQuota == CpuPeriod == 100_000 equivale a exactamente 1 CPU. "
        f"Se obtuvo: {host_cfg.get('CpuQuota')}"
    )


def test_contenedor_tiene_limite_memoria(singleuser_container):
    host_cfg = singleuser_container.attrs["HostConfig"]
    assert host_cfg.get("Memory") == ONE_GB, (
        f"El límite de memoria debe ser {ONE_GB} bytes (1 GB). "
        f"Se obtuvo: {host_cfg.get('Memory')}"
    )


def test_sin_swap_extra(singleuser_container):
    """
    MemorySwap igual a Memory significa que no hay swap adicional asignado.
    Esto impide que el contenedor use disco como memoria de desbordamiento.
    """
    host_cfg = singleuser_container.attrs["HostConfig"]
    mem = host_cfg.get("Memory")
    swap = host_cfg.get("MemorySwap")
    assert mem == swap, (
        f"MemorySwap ({swap}) debe ser igual a Memory ({mem}) para deshabilitar el swap."
    )


def test_volumen_data_esta_montado(singleuser_container):
    mounts = singleuser_container.attrs.get("Mounts", [])
    destinos = [m.get("Destination") for m in mounts]
    assert "/home/jovyan/work/data" in destinos, (
        f"No se encontró un mount en /home/jovyan/work/data. "
        f"Mounts actuales: {destinos}"
    )


def test_volumen_data_es_solo_lectura(singleuser_container):
    mounts = singleuser_container.attrs.get("Mounts", [])
    data_mount = next(
        (m for m in mounts if m.get("Destination") == "/home/jovyan/work/data"),
        None,
    )
    assert data_mount is not None
    assert data_mount.get("RW") is False, (
        "El volumen /data debe ser de solo lectura (RW=False). "
        "Agregar {'bind': '/home/jovyan/work/data', 'mode': 'ro'} en c.DockerSpawner.volumes."
    )


def test_volumen_data_mode_ro(singleuser_container):
    mounts = singleuser_container.attrs.get("Mounts", [])
    data_mount = next(
        (m for m in mounts if m.get("Destination") == "/home/jovyan/work/data"),
        None,
    )
    assert data_mount is not None
    assert data_mount.get("Mode") == "ro", (
        f"El Mode del mount debe ser 'ro', se obtuvo: {data_mount.get('Mode')!r}"
    )


def test_volumen_src_esta_montado(singleuser_container):
    mounts = singleuser_container.attrs.get("Mounts", [])
    destinos = [m.get("Destination") for m in mounts]
    assert "/home/jovyan/work/src" in destinos, (
        f"No se encontró un mount en /home/jovyan/work/src. "
        f"Mounts actuales: {destinos}"
    )
