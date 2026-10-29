from __future__ import annotations

import json
import logging
import time

from src.core.logging import JsonFormatter, get_logger, setup_logging, timed_step


def test_json_formatter() -> None:
    """Verifica se o JsonFormatter gera JSON válido com metadados estruturados."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test_path.py",
        lineno=10,
        msg="Operação finalizada",
        args=(),
        exc_info=None,
    )
    record.duration_s = 1.234
    record.row_count = 500

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert parsed["message"] == "Operação finalizada"
    assert parsed["duration_s"] == 1.234
    assert parsed["row_count"] == 500
    assert "timestamp" in parsed


def test_setup_logging_dev_and_prod() -> None:
    """Garante que a configuração de logging inicializa os handlers esperados."""
    setup_logging(env="dev")
    logger = logging.getLogger()
    assert len(logger.handlers) > 0

    setup_logging(env="prod")
    assert len(logger.handlers) > 0
    assert isinstance(logger.handlers[0].formatter, JsonFormatter)


def test_timed_step_context_manager() -> None:
    """Testa timed_step como gerenciador de contexto medindo tempo e registrando linhas."""
    test_logger = get_logger("test_timed_step")

    with timed_step("etapa_teste", row_count=100, logger_instance=test_logger) as step:
        time.sleep(0.01)
        assert step.name == "etapa_teste"
        step.row_count = 250

    assert step.duration_s > 0
    assert step.row_count == 250


def test_timed_step_decorator() -> None:
    """Testa timed_step como decorator de funções."""
    test_logger = get_logger("test_decorator")

    @timed_step("funcao_decorada", logger_instance=test_logger)
    def dummy_func(x: int, y: int) -> int:
        return x + y

    result = dummy_func(10, 20)
    assert result == 30
