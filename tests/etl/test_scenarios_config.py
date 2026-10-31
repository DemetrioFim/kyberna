from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app
from src.core.paths import reference_data_path
from src.core.scenarios import (
    ScenarioConfig,
    ScenarioNotFoundError,
    ScenarioValidationError,
    list_scenario_configs,
    load_scenario_config,
)
from src.core.types import ScenarioId
from src.etl.scenarios.base import ScenarioBuilder


def test_load_all_four_scenario_yamls_validates_pydantic() -> None:
    """DoD: Garante que os 4 arquivos YAML de cenários são carregados e validados pelo Pydantic."""
    scenarios: list[ScenarioId] = ["c1_toys", "c2_beverages", "c3_retail_chain", "c4_single_store"]

    configs = list_scenario_configs()
    assert len(configs) == 4

    for sc_id in scenarios:
        cfg = load_scenario_config(sc_id)
        assert isinstance(cfg, ScenarioConfig)
        assert cfg.id == sc_id
        assert len(cfg.display_name) > 0
        assert len(cfg.company_profile) > 0


def test_scenario_perspectives_and_specific_capabilities() -> None:
    """Valida as particularidades estratégicas de cada cenário conforme VISION.md §5.4 e §5.5."""
    c1 = load_scenario_config("c1_toys")
    c2 = load_scenario_config("c2_beverages")
    c3 = load_scenario_config("c3_retail_chain")
    c4 = load_scenario_config("c4_single_store")

    # Perspectivas
    assert c1.perspective == "seller"
    assert c2.perspective == "seller"
    assert c3.perspective == "buyer"
    assert c4.perspective == "buyer"

    # Markup de varejo apenas para C3 e C4
    assert c1.retail_markup is None
    assert c2.retail_markup is None
    assert c3.retail_markup is not None and c3.retail_markup > 1.0
    assert c4.retail_markup is not None and c4.retail_markup > 1.0

    # Remanejamento entre filiais: exclusivo do C3
    assert c1.capabilities.branch_transfers is False
    assert c2.capabilities.branch_transfers is False
    assert c3.capabilities.branch_transfers is True
    assert c4.capabilities.branch_transfers is False

    # Eficiência de representantes: Desabilitada no C4 (Loja Única)
    assert c1.capabilities.rep_efficiency is True
    assert c2.capabilities.rep_efficiency is True
    assert c3.capabilities.rep_efficiency is True
    assert c4.capabilities.rep_efficiency is False


def test_scenario_labels_cover_all_ui_keys() -> None:
    """DoD: ScenarioConfig.labels cobre todas as chaves semânticas de negócio necessárias."""
    configs = list_scenario_configs()
    required_label_keys = [
        "customer",
        "customer_plural",
        "product_family",
        "sales_rep",
        "sales_rep_plural",
        "branch",
        "unit",
        "box",
        "order",
        "order_plural",
    ]

    for sc_id, cfg in configs.items():
        labels_dict = cfg.labels.model_dump()
        for key in required_label_keys:
            assert key in labels_dict, f"Cenário {sc_id} não possui o rótulo '{key}'."
            assert isinstance(labels_dict[key], str)
            assert len(labels_dict[key].strip()) > 0


def test_category_maps_referenced_exist() -> None:
    """Garante que qualquer category_map apontado pelos cenários existe em data/reference/."""
    configs = list_scenario_configs()

    for sc_id, cfg in configs.items():
        if cfg.category_map is not None:
            cat_path = reference_data_path(cfg.category_map)
            assert cat_path.exists(), f"Cenário {sc_id} aponta para category_map inexistente: {cat_path}"


def test_load_scenario_config_not_found_raises_readable_error(tmp_path: Path) -> None:
    """DoD: Carregar cenário inexistente lança ScenarioNotFoundError com mensagem legível."""
    with pytest.raises(ScenarioNotFoundError) as exc_info:
        load_scenario_config("cenario_fantasma", scenarios_dir=tmp_path)

    err_msg = str(exc_info.value)
    assert "cenario_fantasma" in err_msg
    assert "não encontrado" in err_msg


def test_load_scenario_config_invalid_yaml_raises_readable_error(tmp_path: Path) -> None:
    """DoD: YAML mal formatado gera ScenarioValidationError legível."""
    bad_yaml = tmp_path / "broken.yaml"
    bad_yaml.write_text("id: broken\n  bad_indent: [missing\n", encoding="utf-8")

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario_config("broken", scenarios_dir=tmp_path)

    assert "Erro de sintaxe" in str(exc_info.value)


def test_load_scenario_config_schema_violation_raises_readable_error(tmp_path: Path) -> None:
    """DoD: YAML com campos faltando ou tipos errados gera ScenarioValidationError legível."""
    incomplete_yaml = tmp_path / "incomplete.yaml"
    incomplete_yaml.write_text(
        """
        id: "c1_toys"
        display_name: "Incompleto"
        # labels está faltando
        """,
        encoding="utf-8",
    )

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario_config("incomplete", scenarios_dir=tmp_path)

    assert "Validação Pydantic falhou" in str(exc_info.value)


def test_scenario_builder_abstract_base_class() -> None:
    """Garante que a classe base ScenarioBuilder exige a implementação do método build."""
    cfg = load_scenario_config("c1_toys")

    # Não deve ser possível instanciar diretamente ScenarioBuilder
    with pytest.raises(TypeError) as exc_info:
        ScenarioBuilder(config=cfg)  # type: ignore[abstract]

    assert "Can't instantiate abstract class ScenarioBuilder" in str(exc_info.value)

    # Subclasse concreta implementando build
    class DummyBuilder(ScenarioBuilder):
        def build(self, con: object) -> dict[str, int]:
            return {"fact_sales": 100}

    dummy = DummyBuilder(config=cfg)
    assert dummy.config.id == "c1_toys"
    assert dummy.build(None) == {"fact_sales": 100}


def test_cli_gold_build_validates_scenario() -> None:
    """Valida que o comando CLI kyberna gold build verifica a existência do cenário."""
    runner = CliRunner()

    # Cenário inválido
    result_invalid = runner.invoke(app, ["gold", "build", "--scenario", "inexistente"])
    assert result_invalid.exit_code != 0
    assert "inexistente" in str(result_invalid.exception)

    # Cenário válido 'all'
    result_all = runner.invoke(app, ["gold", "build", "--scenario", "all"])
    assert result_all.exit_code != 0  # Falha pelo NotImplementedError da M2-D4
    assert "M2-D1" in str(result_all.exception)
