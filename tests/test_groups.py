"""Tests for the presentation-group config and its validation."""
from __future__ import annotations

import pytest

from auditiq.core.groups import GroupIndex, load_default_groups


def test_default_groups_loaded():
    groups = load_default_groups()
    assert "REV_OPERATIONS" in groups
    group = groups.get("REV_OPERATIONS")
    assert group.name == "Revenue from Operations"
    assert group.statement_code == "P&L"
    assert set(group.members) == {"INC_REV_SALES", "INC_REV_SERV", "INC_REV_OTH"}
    assert group.category == "Income"


def test_group_aliases_resolve():
    groups = load_default_groups()
    assert groups.group_for("Revenue from Operations") == "REV_OPERATIONS"
    assert groups.group_for("Turnover") == "REV_OPERATIONS"
    assert groups.group_for("Trade Receivables") is None
    assert groups.groups_of("INC_REV_SERV") == ("REV_OPERATIONS",)
    assert groups.groups_of("AST_TR") == ()


def test_group_normal_balance_from_members():
    from auditiq.core import load_default_taxonomy

    groups = load_default_groups()
    taxonomy = load_default_taxonomy()
    assert groups.normal_balance("REV_OPERATIONS", taxonomy).lower().startswith("credit")


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_unknown_fsli_member_rejected(tmp_path):
    path = _write(
        tmp_path,
        "groups.csv",
        "group_code,group_name,statement,fsli_code\n"
        "G1,Agg,Statement of Profit and Loss,INC_REV_SALES\n"
        "G1,Agg,Statement of Profit and Loss,NOPE\n",
    )
    aliases = _write(tmp_path, "aliases.csv", "alias,group_code\n")
    with pytest.raises(ValueError, match="unknown FSLI"):
        GroupIndex.from_csv(path, aliases)


def test_disjoint_membership_enforced(tmp_path):
    path = _write(
        tmp_path,
        "groups.csv",
        "group_code,group_name,statement,fsli_code\n"
        "G1,Agg,Statement of Profit and Loss,INC_REV_SALES\n"
        "G1,Agg,Statement of Profit and Loss,INC_REV_SERV\n"
        "G2,Other,Statement of Profit and Loss,INC_REV_SERV\n"
        "G2,Other,Statement of Profit and Loss,INC_REV_OTH\n",
    )
    aliases = _write(tmp_path, "aliases.csv", "alias,group_code\n")
    with pytest.raises(ValueError, match="disjoint"):
        GroupIndex.from_csv(path, aliases)


def test_single_member_group_rejected(tmp_path):
    path = _write(
        tmp_path,
        "groups.csv",
        "group_code,group_name,statement,fsli_code\n"
        "G1,Agg,Statement of Profit and Loss,INC_REV_SALES\n",
    )
    aliases = _write(tmp_path, "aliases.csv", "alias,group_code\n")
    with pytest.raises(ValueError, match="at least two"):
        GroupIndex.from_csv(path, aliases)


def test_alias_to_unknown_group_rejected(tmp_path):
    path = _write(
        tmp_path,
        "groups.csv",
        "group_code,group_name,statement,fsli_code\n"
        "G1,Agg,Statement of Profit and Loss,INC_REV_SALES\n"
        "G1,Agg,Statement of Profit and Loss,INC_REV_SERV\n",
    )
    aliases = _write(tmp_path, "aliases.csv", "alias,group_code\nturnover,GHOST\n")
    with pytest.raises(ValueError, match="unknown group"):
        GroupIndex.from_csv(path, aliases)


def test_absent_config_yields_empty_index(tmp_path):
    groups = load_default_groups(path=tmp_path / "missing.csv")
    assert len(groups) == 0
    assert groups.group_for("Revenue from Operations") is None
