"""Cuentas de Mosquitto (passwd con mosquitto_passwd simulado) y ACL desde plantilla (14.2)."""

from __future__ import annotations

import logging
import stat

import pytest
from privd_testkit import Env, fail, fake_mosquitto_passwd, ok

from commands import mosquitto
from commands.core import CommandError

GOOD_PASSWORD = "Abcdefgh1234-xyz"


def setup_passwd(env: Env) -> None:
    env.runner.on([env.ctx.bins.mosquitto_passwd], fake_mosquitto_passwd)


def passwd_lines(env: Env) -> list[str]:
    return env.ctx.paths.mosquitto_passwd.read_text().splitlines()


def code_of(exc: pytest.ExceptionInfo[CommandError]) -> str:
    return exc.value.code


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("password", ["a" * 12, "a" * 128, "con espacio adentro", "!#$%&'()*+,-./"])
def test_valid_passwords(password: str) -> None:
    assert mosquitto.validate_password(password) == password


@pytest.mark.parametrize(
    "password",
    [
        "a" * 11,
        "a" * 129,
        "tiene:dospuntos",
        "salto\nde-linea12",
        "retorno\rcarro123",
        "tab\taaaaaaaaaaa",
        "ñandú-no-ascii-123",
        " empieza-con-espacio",
        "termina-con-espacio ",
        12345678901234,
        None,
    ],
)
def test_invalid_passwords(password: object) -> None:
    with pytest.raises(CommandError) as exc:
        mosquitto.validate_password(password)
    assert code_of(exc) == "invalid_args"


@pytest.mark.parametrize(
    "username",
    ["Gw-casa", "ab", "-gw", "_gw", "gw casa", "gw;rm", "gw/../x", "a" * 33, "", "gw\n", 5],
)
def test_invalid_usernames(env: Env, username: object) -> None:
    with pytest.raises(CommandError) as exc:
        mosquitto.account_set(env.ctx, {"username": username, "password": GOOD_PASSWORD})
    assert code_of(exc) == "invalid_args"
    assert env.runner.calls == []


def test_missing_and_unknown_args(env: Env) -> None:
    with pytest.raises(CommandError):
        mosquitto.account_set(env.ctx, {"username": "gw-casa"})
    with pytest.raises(CommandError):
        mosquitto.account_set(
            env.ctx, {"username": "gw-casa", "password": GOOD_PASSWORD, "admin": True}
        )


# ---------------------------------------------------------------------------
# passwd
# ---------------------------------------------------------------------------


def test_account_set_creates_hashed_entry(env: Env) -> None:
    setup_passwd(env)
    result = mosquitto.account_set(env.ctx, {"username": "gw-casa", "password": GOOD_PASSWORD})
    assert result == {"username": "gw-casa", "created": True}
    lines = passwd_lines(env)
    assert len(lines) == 1
    assert lines[0].startswith("gw-casa:$7$101$")
    assert GOOD_PASSWORD not in env.ctx.paths.mosquitto_passwd.read_text()
    # La clave nunca va por la línea de comandos ni por stdin.
    assert GOOD_PASSWORD not in env.runner.all_text()
    (call,) = env.runner.calls
    assert call.argv[:2] == ["/usr/bin/mosquitto_passwd", "-U"]
    assert call.umask == 0o077
    # El temporal estuvo en /etc/mosquitto (mismo sistema de archivos) y ya no existe.
    assert str(env.ctx.paths.mosquitto_dir) in call.argv[2]
    leftovers = [p.name for p in env.ctx.paths.mosquitto_dir.iterdir()]
    assert sorted(leftovers) == ["conf.d", "passwd"]
    assert ("passwd", "mosquitto", "mosquitto") in [
        (name.split(".")[1] if name.startswith(".") else name, u, g)
        for name, u, g in env.owner.calls
    ]


@pytest.mark.linux
def test_passwd_permissions(env: Env) -> None:
    setup_passwd(env)
    mosquitto.account_set(env.ctx, {"username": "gw-casa", "password": GOOD_PASSWORD})
    mode = stat.S_IMODE(env.ctx.paths.mosquitto_passwd.stat().st_mode)
    assert mode == 0o640


def test_account_set_replaces_and_preserves_others(env: Env) -> None:
    setup_passwd(env)
    env.ctx.paths.mosquitto_passwd.write_text(
        "gw-heltec:$7$101$aaa$bbb\n"
        "\n"
        "dbg-dev:$7$101$ccc$ddd\n"
        "gw-casa:$7$101$viejo$hash\n"
        "gw-casa:$7$101$duplicado$hash\n"
    )
    result = mosquitto.account_set(env.ctx, {"username": "gw-casa", "password": GOOD_PASSWORD})
    assert result["created"] is False
    lines = passwd_lines(env)
    assert lines[0] == "gw-heltec:$7$101$aaa$bbb"
    assert lines[1] == "dbg-dev:$7$101$ccc$ddd"
    assert len(lines) == 3
    assert lines[2].startswith("gw-casa:$7$101$")
    assert "viejo" not in lines[2]


def test_account_set_failure_keeps_passwd(env: Env) -> None:
    env.ctx.paths.mosquitto_passwd.write_text("gw-heltec:$7$101$aaa$bbb\n")
    env.runner.on([env.ctx.bins.mosquitto_passwd], fail(1, "Error: Corrupt password file"))
    with pytest.raises(CommandError) as exc:
        mosquitto.account_set(env.ctx, {"username": "gw-casa", "password": GOOD_PASSWORD})
    assert code_of(exc) == "command_failed"
    assert "Corrupt" in exc.value.message
    assert passwd_lines(env) == ["gw-heltec:$7$101$aaa$bbb"]
    assert sorted(p.name for p in env.ctx.paths.mosquitto_dir.iterdir()) == ["conf.d", "passwd"]


def test_account_set_rejects_unconverted_output(env: Env) -> None:
    env.runner.on([env.ctx.bins.mosquitto_passwd], ok())  # no convierte: queda la clave en claro
    with pytest.raises(CommandError) as exc:
        mosquitto.account_set(env.ctx, {"username": "gw-casa", "password": GOOD_PASSWORD})
    assert "inesperado" in exc.value.message
    assert not env.ctx.paths.mosquitto_passwd.exists()


def test_account_delete(env: Env) -> None:
    env.ctx.paths.mosquitto_passwd.write_text("gw-heltec:$7$h\ngw-casa:$7$h\n")
    assert mosquitto.account_delete(env.ctx, {"username": "gw-casa"}) == {
        "username": "gw-casa",
        "deleted": True,
    }
    assert passwd_lines(env) == ["gw-heltec:$7$h"]
    assert mosquitto.account_delete(env.ctx, {"username": "gw-casa"})["deleted"] is False


def test_account_delete_creates_missing_file(env: Env) -> None:
    assert mosquitto.account_delete(env.ctx, {"username": "gw-casa"})["deleted"] is False
    assert env.ctx.paths.mosquitto_passwd.read_text() == ""


def test_account_list_only_names(env: Env) -> None:
    env.ctx.paths.mosquitto_passwd.write_text(
        "gw-heltec:$7$101$secreto$hash\ndbg-dev:$7$101$otro$hash\n# comentario\n"
    )
    result = mosquitto.account_list(env.ctx, {})
    assert result == {"accounts": [{"username": "dbg-dev"}, {"username": "gw-heltec"}]}
    assert "secreto" not in str(result)


def test_account_list_without_file(env: Env) -> None:
    assert mosquitto.account_list(env.ctx, {}) == {"accounts": []}


# ---------------------------------------------------------------------------
# ACL
# ---------------------------------------------------------------------------

ACCOUNTS = [
    {"username": "meshbox-ingest", "purpose": "ingest"},
    {"username": "gw-heltec", "purpose": "gateway"},
    {"username": "int-ejemplo", "purpose": "integration"},
    {"username": "dbg-dev", "purpose": "debug"},
]


def test_acl_render_template(env: Env) -> None:
    result = mosquitto.acl_write(env.ctx, {"root": "msh/AR/viedma", "accounts": ACCOUNTS})
    assert result["accounts"] == 4
    text = env.ctx.paths.mosquitto_acl.read_text()
    assert text == (
        "# Generado por meshbox-privd. No editar a mano: el panel de meshbox lo reescribe.\n"
        "# root=msh/AR/viedma events_prefix=meshbox\n"
        "\n"
        "user dbg-dev\n"
        "topic read msh/AR/viedma/#\n"
        "\n"
        "user gw-heltec\n"
        "topic readwrite msh/AR/viedma/#\n"
        "\n"
        "user int-ejemplo\n"
        "topic read meshbox/events/#\n"
        "\n"
        "user meshbox-ingest\n"
        "topic read msh/AR/viedma/#\n"
        "topic write meshbox/#\n"
    )
    assert result["bytes"] == len(text.encode())
    assert ("acl", "mosquitto", "mosquitto") in [
        (n.split(".")[1] if n.startswith(".") else n, u, g) for n, u, g in env.owner.calls
    ]


def test_acl_custom_events_prefix(env: Env) -> None:
    mosquitto.acl_write(
        env.ctx,
        {
            "root": "msh/AR/viedma",
            "events_prefix": "casa/meshbox",
            "accounts": [{"username": "int-ejemplo", "purpose": "integration"}],
        },
    )
    assert "topic read casa/meshbox/events/#" in env.ctx.paths.mosquitto_acl.read_text()


def test_acl_empty_accounts(env: Env) -> None:
    mosquitto.acl_write(env.ctx, {"root": "msh/AR/viedma", "accounts": []})
    assert "user" not in env.ctx.paths.mosquitto_acl.read_text()


@pytest.mark.linux
def test_acl_permissions(env: Env) -> None:
    mosquitto.acl_write(env.ctx, {"root": "msh/AR/viedma", "accounts": ACCOUNTS})
    assert stat.S_IMODE(env.ctx.paths.mosquitto_acl.stat().st_mode) == 0o640


@pytest.mark.parametrize(
    "root",
    [
        "msh/#",
        "msh/+/x",
        "/msh/AR",
        "msh/AR/",
        "msh//AR",
        "msh/../etc",
        "msh AR",
        "msh/AR\nuser x",
        "",
        "a" * 65,
        "msh/ÁR",
        None,
    ],
)
def test_acl_invalid_root(env: Env, root: object) -> None:
    with pytest.raises(CommandError) as exc:
        mosquitto.acl_write(env.ctx, {"root": root, "accounts": []})
    assert code_of(exc) == "invalid_args"
    assert not env.ctx.paths.mosquitto_acl.exists()


@pytest.mark.parametrize(
    "accounts",
    [
        "no-es-lista",
        [{"username": "gw-casa", "purpose": "admin"}],
        [{"username": "gw-casa"}],
        [{"username": "gw-casa", "purpose": "gateway", "acl": "topic readwrite #"}],
        [{"username": "GW", "purpose": "gateway"}],
        ["gw-casa"],
        [
            {"username": "gw-casa", "purpose": "gateway"},
            {"username": "gw-casa", "purpose": "debug"},
        ],
        [{"username": f"gw-{i:03d}", "purpose": "gateway"} for i in range(257)],
    ],
)
def test_acl_invalid_accounts(env: Env, accounts: object) -> None:
    with pytest.raises(CommandError) as exc:
        mosquitto.acl_write(env.ctx, {"root": "msh/AR/viedma", "accounts": accounts})
    assert code_of(exc) == "invalid_args"


def test_acl_rejects_raw_text(env: Env) -> None:
    with pytest.raises(CommandError):
        mosquitto.acl_write(env.ctx, {"rules": "topic readwrite #"})


def test_acl_warns_about_omitted_accounts(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    env.ctx.paths.mosquitto_passwd.write_text("gw-heltec:$7$h\ndbg-dev:$7$h\nmeshbox-ingest:$7$h\n")
    with caplog.at_level(logging.WARNING, logger="privd.mosquitto"):
        result = mosquitto.acl_write(
            env.ctx,
            {
                "root": "msh/AR/viedma",
                "accounts": [{"username": "meshbox-ingest", "purpose": "ingest"}],
            },
        )
    assert result["omitted"] == ["dbg-dev", "gw-heltec"]
    assert "dbg-dev, gw-heltec" in caplog.text
    # Igual se renderiza tal como vino.
    assert "gw-heltec" not in env.ctx.paths.mosquitto_acl.read_text()


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------


def test_reload(env: Env) -> None:
    assert mosquitto.reload(env.ctx, {}) == {"reloaded": True}
    assert env.runner.argvs() == [["/usr/bin/systemctl", "reload", "mosquitto.service"]]


def test_reload_failure(env: Env) -> None:
    env.runner.on(["/usr/bin/systemctl", "reload"], fail(1, "Job for mosquitto.service failed"))
    with pytest.raises(CommandError) as exc:
        mosquitto.reload(env.ctx, {})
    assert exc.value.code == "command_failed"
    assert "mosquitto.service failed" in exc.value.message


SHOW_OUTPUT = (
    "Id=mosquitto.service\nLoadState=loaded\nActiveState=active\nSubState=running\n"
    "UnitFileState=enabled\nMainPID=812\nNRestarts=0\nResult=success\n"
    "ActiveEnterTimestamp=@1792465562\n"
)


def test_status(env: Env) -> None:
    env.runner.on(["/usr/bin/systemctl", "show"], ok(SHOW_OUTPUT))
    env.ctx.paths.mosquitto_passwd.write_text("gw-heltec:$7$h\n")
    result = mosquitto.status(env.ctx, {})
    assert result == {
        "unit": "mosquitto.service",
        "load": "loaded",
        "active": "active",
        "sub": "running",
        "enabled": "enabled",
        "pid": 812,
        "restarts": 0,
        "result": "success",
        "since": 1792465562,
        "accounts": ["gw-heltec"],
        "acl_present": False,
    }
    argv = env.runner.argvs()[0]
    assert argv[:3] == ["/usr/bin/systemctl", "show", "mosquitto.service"]
    assert "--timestamp=unix" in argv


def test_status_inactive_unit(env: Env) -> None:
    env.runner.on(
        ["/usr/bin/systemctl", "show"],
        ok("ActiveState=inactive\nMainPID=0\nNRestarts=x\nActiveEnterTimestamp=\n"),
    )
    result = mosquitto.status(env.ctx, {})
    assert result["pid"] is None
    assert result["restarts"] is None
    assert result["since"] is None
