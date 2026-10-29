from __future__ import annotations

import duckdb
import pandas as pd
import pyarrow as pa

import src
import src.cli
import src.core
import src.db
import src.etl
import src.ml
import src.services
import src.ui


def test_core_packages_importable() -> None:
    """Verifica se os pacotes do núcleo analítico funcionam corretamente."""
    con = duckdb.connect(":memory:")
    res = con.execute("SELECT 42 AS value").fetchone()
    assert res is not None and res[0] == 42

    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    table = pa.Table.from_pandas(df)
    assert len(table) == 3


def test_kyberna_modules_importable() -> None:
    """Verifica se a árvore de pacotes do projeto src está íntegra."""
    assert src is not None
    assert src.cli is not None
    assert src.core is not None
    assert src.db is not None
    assert src.etl is not None
    assert src.ml is not None
    assert src.services is not None
    assert src.ui is not None
