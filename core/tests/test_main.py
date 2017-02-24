from __future__ import print_function, unicode_literals
import os
import six
import pytest
from autocrypt import mime


@pytest.fixture
def account_dir(tmpdir):
    return tmpdir.join("account").strpath


@pytest.fixture
def mycmd(cmd, tmpdir, request):
    cmd.set_basedir(tmpdir.mkdir("account").strpath)
    return cmd


def test_help(cmd):
    cmd.run_ok([], """
        *init*
        *make-header*
        *export-public-key*
        *export-secret-key*
    """)
    cmd.run_ok(["--help"], """
        *access and manage*
    """)


def test_init_help(cmd):
    cmd.run_ok(["init", "--help"], """
        *init*
    """)


def test_init(mycmd):
    mycmd.run_ok(["init"], """
            *account*created*
            *gpgmode*own*
    """)
    mycmd.run_fail(["init"], """
            *account*exists*
    """)
    mycmd.run_ok(["init", "--replace"], """
            *deleting account dir*
            *account*created*
    """)


def test_init_existing_key_native_gpg(mycmd, monkeypatch, bingpg, gpgpath):
    adr = "x@y.org"
    keyhandle = bingpg.gen_secret_key(adr)
    monkeypatch.setenv("GNUPGHOME", bingpg.homedir)
    mycmd.run_ok(["init", "--use-existing-key", adr, "--gpgbin=%s" % gpgpath], """
            *account*created*
            *own-keyhandle*{}*
            *gpgbin*{}*
            *gpgmode*system*
    """.format(keyhandle, gpgpath))
    mycmd.run_ok(["make-header", adr], """
        *Autocrypt*to=x@y.org*
    """)


def test_init_and_make_header(mycmd):
    mycmd.run_fail(["make-header", "xyz"], """
        *Account*not initialized*
    """)
    adr = "x@yz.org"
    mycmd.run_ok(["init"])
    out = mycmd.run_ok(["make-header", adr])
    d = mime.parse_one_ac_header_from_string(out)
    assert "prefer-encrypt" not in out
    assert "type" not in out
    assert d["to"] == adr
    out2 = mycmd.run_ok(["make-header", adr])
    assert out == out2


def test_init_and_make_header_with_envvar(cmd, tmpdir):
    with tmpdir.as_cwd():
        os.environ["AUTOCRYPT_BASEDIR"] = "."
        test_init_and_make_header(cmd)


def test_set_prefer_encrypt(mycmd):
    mycmd.run_ok(["init"])
    mycmd.run_ok(["set-prefer-encrypt"], """
        *notset*
    """)
    mycmd.run_ok(["set-prefer-encrypt", "yes"])
    mycmd.run_ok(["set-prefer-encrypt"], """
        *yes*
    """)
    adr = "x@yz.org"
    out3 = mycmd.run_ok(["make-header", adr])
    d3 = mime.parse_one_ac_header_from_string(out3)
    assert d3["prefer-encrypt"] == "yes"


def test_exports_and_status(mycmd):
    mycmd.run_ok(["init"])
    out = mycmd.run_ok(["export-public-key"])
    check_ascii(out)
    out = mycmd.run_ok(["export-secret-key"])
    check_ascii(out)
    out = mycmd.run_ok(["status"], """
        account-dir:*
        uuid:*
        own-keyhandle:*
        prefer-encrypt: notset
    """)


def check_ascii(out):
    if isinstance(out, six.text_type):
        out.encode("ascii")
    else:
        out.decode("ascii")


def test_process_incoming(mycmd, datadir):
    mycmd.run_ok(["init"])
    fn = datadir.join("rsa2048-simple.eml")
    mycmd.run_ok(["process-incoming", fn], """
        *processed mail*alice@testsuite.autocrypt.org*key*BAFC533CD993BD7F*
    """)
    out1 = mycmd.run_ok(["export-public-key", "alice@testsuite.autocrypt.org"], """
        *---BEGIN PGP*
    """)
    out2 = mycmd.run_ok(["export-public-key", "BAFC533CD993BD7F"], """
        *---BEGIN PGP*
    """)
    assert out1 == out2

    mycmd.run_ok(["status"], """
        *---peers---*
        alice@testsuite.autocrypt.org*D993BD7F*1636 bytes*prefer-encrypt*
    """)


class TestProcessOutgoing:
    def test_simple(self, mycmd, datadir, gen_mail):
        mycmd.run_ok(["init"])
        mail = gen_mail()
        out1 = mycmd.run_ok(["process-outgoing"], input=mail.as_string())
        m = mime.parse_message_from_string(out1)
        assert len(m.get_all("Autocrypt")) == 1
        found_header = "Autocrypt: " + m["Autocrypt"]
        gen_header = mycmd.run_ok(["make-header", "a@a.org"])
        x1 = mime.parse_one_ac_header_from_string(gen_header)
        x2 = mime.parse_one_ac_header_from_string(found_header)
        assert x1 == x2

    def test_simple_dont_replace(self, mycmd, datadir, gen_mail):
        mycmd.run_ok(["init"])
        mail = gen_mail()
        gen_header = mycmd.run_ok(["make-header", "x@x.org"])
        mail.add_header("Autocrypt", gen_header)

        out1 = mycmd.run_ok(["process-outgoing"], input=mail.as_string())
        m = mime.parse_message_from_string(out1)
        assert len(m.get_all("Autocrypt")) == 1
        x1 = mime.parse_ac_headervalue(m["Autocrypt"])
        x2 = mime.parse_ac_headervalue(gen_header)
        assert x1 == x2
