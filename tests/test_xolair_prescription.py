from src.xolair import build_xolair_prescription


def normalize(lst):
    # convert list of dicts to mapping for easier assertions
    return {item['drug_name']: item['qty'] for item in lst}


def test_xolair_150():
    out = build_xolair_prescription(150)
    m = normalize(out)
    assert m == {"ゾレア皮下注１５０ｍｇペン": 1}


def test_xolair_225():
    out = build_xolair_prescription(225)
    m = normalize(out)
    assert m == {"ゾレア皮下注１５０ｍｇペン": 2}


def test_xolair_300():
    out = build_xolair_prescription(300)
    m = normalize(out)
    assert m == {"ゾレア皮下注３００ｍｇペン": 1}


def test_xolair_375():
    out = build_xolair_prescription(375)
    m = normalize(out)
    assert m == {"ゾレア皮下注７５ｍｇペン": 1, "ゾレア皮下注３００ｍｇペン": 1}
