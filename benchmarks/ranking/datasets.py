"""The public data sets of the ranking benchmark: where each comes from and how it is read.

Nothing here is bundled with KATO. A data set is downloaded from its original
host the first time a run needs it, checked against a pinned SHA-256, and read
as a stream straight out of its archive: nothing is unpacked to disk.

A data set is turned into sequences of events, one symbol per event. Each
defines which sequences the node learns and which are held out for queries.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import ssl
import tarfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

# A learned sequence is cut to its first MAX_EVENTS events, as in the study the
# benchmark follows. Queries are taken from the same stretch of a held-out one.
MAX_EVENTS = 100

_PLAIN = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.+-")


def symbol(token: str) -> str:
    """The KATO symbol for one token of a source.

    Letters, digits and ``_ . + -`` are kept; any other character becomes %XX of
    its UTF-8 bytes. The mapping is one to one, so two tokens are the same
    symbol exactly when they are the same token, and no data set can trip a
    quoting rule anywhere between the client and the stores.
    """
    out = []
    for character in token:
        if character in _PLAIN:
            out.append(character)
        else:
            out.extend(f"%{byte:02X}" for byte in character.encode("utf-8"))
    return "".join(out)


@dataclass(frozen=True)
class Download:
    """One file to fetch. `sha256` pins the file itself; `members` pins files inside a zip.

    A zip from a repository can be rebuilt by its host with new timestamps, so
    for those the pin is on the member that is read, not on the container.
    """
    url: str
    filename: str
    size: int
    sha256: str = ""
    members: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Split:
    """The sequences a node learns and the sequences held out for queries."""
    learn: list
    held_out: list


@dataclass(frozen=True)
class Dataset:
    key: str
    title: str
    kind: str                 # how the report groups it: 'System logs', 'Music', ...
    in_fit: bool              # True if the weights of `potential` were fitted on this data set
    what: str                 # one line: what a sequence and an event are
    licence: str
    page: str                 # the data set's own page
    cite: str
    downloads: tuple[Download, ...]
    read: Callable[[Path], Split] = field(repr=False, compare=False, default=None)


# ----------------------------------------------------------------------------
# fetching

def _sha256_of(stream) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1 << 20), b""):
        digest.update(block)
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return _sha256_of(stream)


def verify(download: Download, path: Path) -> None:
    """Raise ValueError unless `path` holds exactly the bytes the benchmark was built on."""
    if download.sha256:
        found = _file_sha256(path)
        if found != download.sha256:
            raise ValueError(
                f"{path.name}: SHA-256 is {found}, expected {download.sha256}. "
                f"The file at {download.url} has changed or the download is incomplete."
            )
    if download.members:
        with zipfile.ZipFile(path) as archive:
            for member, expected in download.members:
                with archive.open(member) as stream:
                    found = _sha256_of(stream)
                if found != expected:
                    raise ValueError(
                        f"{path.name}:{member}: SHA-256 is {found}, expected {expected}. "
                        f"The file at {download.url} has changed."
                    )


def _open(request: urllib.request.Request):
    """Open an HTTPS request with the server's certificate verified.

    Some Python builds come without CA certificates (python.org's for macOS,
    until its "Install Certificates" command has been run). There the bundle of
    the `certifi` package is used when that package is installed. Verification
    is never turned off.
    """
    try:
        return urllib.request.urlopen(request, timeout=120)
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        try:
            import certifi
        except ImportError:
            raise ValueError(
                f"{request.full_url}: the server's certificate could not be verified, because this Python "
                "has no CA certificates. Install them (python.org's Python for macOS: run its "
                "'Install Certificates.command'; any Python: `pip install certifi`) and run again."
            ) from error
        return urllib.request.urlopen(request, timeout=120, context=ssl.create_default_context(cafile=certifi.where()))


def fetch(download: Download, data_dir: Path, log=print) -> Path:
    """The local path of a download, fetching it first if it is not there. Verified either way."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / download.filename
    if not path.exists():
        if not download.url.startswith("https://"):
            raise ValueError(f"refusing to fetch a non-HTTPS URL: {download.url}")
        log(f"    downloading {download.filename} ({download.size / 1e6:.1f} MB) from {download.url}")
        partial = path.with_name(path.name + ".part")
        request = urllib.request.Request(download.url, headers={"User-Agent": "kato-ranking-benchmark"})
        with _open(request) as response, partial.open("wb") as out:
            for block in iter(lambda: response.read(1 << 20), b""):
                out.write(block)
        partial.replace(path)
    try:
        verify(download, path)
    except (ValueError, zipfile.BadZipFile, KeyError) as error:
        raise ValueError(
            f"{error}\nDelete {path} to download it again. If the check still fails, the source "
            f"has changed and this data set cannot be compared with earlier runs."
        ) from error
    return path


def discard(dataset: Dataset, data_dir: Path) -> None:
    """Remove a data set's downloads from the benchmark's own data folder."""
    for download in dataset.downloads:
        path = data_dir / download.filename
        if path.exists():
            path.unlink()


# ----------------------------------------------------------------------------
# splitting

def learnable(sequences: list) -> list:
    """Sequences of two or more events, each cut to its first MAX_EVENTS."""
    return [sequence[:MAX_EVENTS] for sequence in sequences if len(sequence) >= 2]


def split_by_index(sequences: list, modulus: int, learn: tuple, held_out: tuple) -> Split:
    """Sequence j is learned or held out by j % modulus. Residues in neither group are not used.

    Learned sequences are cut to MAX_EVENTS. Held-out sequences are kept whole,
    so a query can tell a sequence that ended from one that was cut.
    """
    if set(learn) & set(held_out):
        raise ValueError("a sequence cannot be both learned and held out")
    return Split(
        learn=learnable([s for j, s in enumerate(sequences) if j % modulus in learn]),
        held_out=[s for j, s in enumerate(sequences) if j % modulus in held_out and len(s) >= 2],
    )


# ----------------------------------------------------------------------------
# readers: each returns every sequence of the source, in file order

def read_hdfs_traces(stream) -> list:
    """Rows of Loghub's Event_traces.csv: one block's log events, in order, as template ids."""
    sequences = []
    for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8", newline="")):
        tokens = [token.strip() for token in row["Features"].strip("[]").split(",")]
        sequences.append([[symbol(token)] for token in tokens if token])
    return sequences


def read_msnbc(stream) -> list:
    """msnbc990928.seq: after the '% Sequences' header, one user's page categories per line."""
    sequences, started = [], False
    for line in io.TextIOWrapper(stream, encoding="latin-1"):
        if line.startswith("% Sequences"):
            started = True
        elif started and line.strip():
            sequences.append([[f"c{int(token):02d}"] for token in line.split()])
    return sequences


def read_wikitext_sentences(stream) -> list:
    """Sentences of a WikiText file: the tokens up to and including each ' . ', headings skipped."""
    sequences = []
    for line in io.TextIOWrapper(stream, encoding="utf-8"):
        tokens = line.split()
        if not tokens or tokens[0] == "=":
            continue
        sentence = []
        for token in tokens:
            sentence.append([symbol(token)])
            if token == ".":
                sequences.append(sentence)
                sentence = []
        if sentence:
            sequences.append(sentence)
    return sequences


def read_xes_traces(stream, keys: tuple) -> list:
    """Traces of an XES event log. An event's symbol joins the values of `keys` with '+'."""
    sequences, events, values = [], None, None
    for action, element in ElementTree.iterparse(stream, events=("start", "end")):
        tag = element.tag.rsplit("}", 1)[-1]
        if action == "start":
            if tag == "trace":
                events = []
            elif tag == "event":
                values = {}
        elif tag == "event":
            if events is not None and values is not None:
                events.append([symbol("+".join(values.get(key, "") for key in keys))])
            values = None
            element.clear()
        elif tag == "trace":
            sequences.append(events)
            events = None
            element.clear()
        elif values is not None and element.get("key") in keys:
            values[element.get("key")] = element.get("value", "")
    return sequences


def read_unix_sessions(stream) -> list:
    """UNIX_user_data.tar.gz: per user, a gzipped token stream; **SOF** and **EOF** bound a shell session.

    The tar is read as a stream and nothing is written to disk. A sequence is
    one session, in the order the users and their sessions appear.
    """
    sequences = []
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith(".gz"):
                continue
            session = None
            for line in io.TextIOWrapper(gzip.GzipFile(fileobj=archive.extractfile(member)), encoding="latin-1"):
                token = line.strip()
                if token == "**SOF**":
                    session = []
                elif token == "**EOF**":
                    if session is not None:
                        sequences.append(session)
                    session = None
                elif token and session is not None:
                    session.append([symbol(token)])
    return sequences


def read_bach_chords(stream) -> list:
    """jsbach_chorals_harmony.data: one row per event; a chorale's chord labels in order.

    A chord that sounds over several events is one event here: runs of the same
    label are merged, so a sequence is the chorale's chord progression.
    """
    sequences, current, previous = [], None, None
    for row in csv.reader(io.TextIOWrapper(stream, encoding="latin-1")):
        if len(row) < 17:
            continue
        chorale, chord = row[0].strip(), symbol(row[16].strip())
        if chorale != current:
            sequences.append([])
            current, previous = chorale, None
        if chord != previous:
            sequences[-1].append([chord])
            previous = chord
    return sequences


# ----------------------------------------------------------------------------
# the data sets

def _hdfs(data_dir: Path, log=print) -> Split:
    path = fetch(HDFS.downloads[0], data_dir, log)
    with zipfile.ZipFile(path) as archive, archive.open("preprocessed/Event_traces.csv") as stream:
        return split_by_index(read_hdfs_traces(stream), 70, (0,), (35,))


def _msnbc(data_dir: Path, log=print) -> Split:
    path = fetch(MSNBC.downloads[0], data_dir, log)
    with zipfile.ZipFile(path) as archive, archive.open("msnbc990928.seq.gz") as member:
        return split_by_index(read_msnbc(gzip.GzipFile(fileobj=member)), 100, (0,), (50,))


def _wikitext(data_dir: Path, log=print) -> Split:
    learn_path = fetch(WIKITEXT.downloads[0], data_dir, log)
    held_path = fetch(WIKITEXT.downloads[1], data_dir, log)
    with learn_path.open("rb") as stream:
        learn = split_by_index(read_wikitext_sentences(stream), 2, (0,), ()).learn
    with held_path.open("rb") as stream:
        held_out = [s for s in read_wikitext_sentences(stream) if len(s) >= 2]
    return Split(learn=learn, held_out=held_out)


def _bpi2012(data_dir: Path, log=print) -> Split:
    path = fetch(BPI2012.downloads[0], data_dir, log)
    with gzip.open(path, "rb") as stream:
        return split_by_index(read_xes_traces(stream, ("concept:name", "lifecycle:transition")), 4, (0, 1), (3,))


def _sepsis(data_dir: Path, log=print) -> Split:
    path = fetch(SEPSIS.downloads[0], data_dir, log)
    with gzip.open(path, "rb") as stream:
        return split_by_index(read_xes_traces(stream, ("concept:name",)), 5, (0, 1, 2, 3), (4,))


def _bach(data_dir: Path, log=print) -> Split:
    path = fetch(BACH.downloads[0], data_dir, log)
    with zipfile.ZipFile(path) as archive, archive.open("jsbach_chorals_harmony.data") as stream:
        return split_by_index(read_bach_chords(stream), 5, (0, 1, 2, 3), (4,))


def _unix(data_dir: Path, log=print) -> Split:
    path = fetch(UNIX.downloads[0], data_dir, log)
    with zipfile.ZipFile(path) as archive, archive.open("UNIX_user_data.tar.gz") as stream:
        return split_by_index(read_unix_sessions(stream), 10, (0, 2, 4, 6, 8), (5,))


HDFS = Dataset(
    key="hdfs",
    title="HDFS block traces",
    kind="System logs",
    in_fit=True,
    what="One sequence per HDFS block: its log events in order, each event a log template id. "
         "One trace in 70 is learned, one in 70 held out.",
    licence="CC BY 4.0 on the Zenodo record; Loghub asks that the data be used for research or "
            "academic work and that its paper be cited",
    page="https://doi.org/10.5281/zenodo.8196385",
    cite="Zhu, He, He, Liu and Lyu, Loghub: A Large Collection of System Log Datasets for AI-driven "
         "Log Analytics, ISSRE 2023 (https://arxiv.org/abs/2008.06448); the logs are from Xu, Huang, "
         "Fox, Patterson and Jordan, SOSP 2009",
    downloads=(Download(
        url="https://zenodo.org/records/8196385/files/HDFS_v1.zip?download=1",
        filename="HDFS_v1.zip",
        size=186645559,
        sha256="04f919f2185821f23f045dca611a7586429bdabc601bd7b43f30005f8e289b01",
    ),),
    read=_hdfs,
)

MSNBC = Dataset(
    key="msnbc",
    title="msnbc.com page visits",
    kind="Click streams",
    in_fit=True,
    what="One sequence per visitor on 28 September 1999: the page categories requested, in order "
         "(17 categories). One visitor in 100 is learned, one in 100 held out.",
    licence="CC BY 4.0",
    page="https://archive.ics.uci.edu/dataset/133/msnbc+com+anonymous+web+data",
    cite="Heckerman, msnbc.com Anonymous Web Data, UCI Machine Learning Repository",
    downloads=(Download(
        url="https://archive.ics.uci.edu/static/public/133/msnbc+com+anonymous+web+data.zip",
        filename="msnbc_com_anonymous_web_data.zip",
        size=2356626,
        members=(("msnbc990928.seq.gz", "d0ad0edf726fe265f956b43d2d02bf07b58b5c27df3fdbc7b02b7195061374a2"),),
    ),),
    read=_msnbc,
)

_WIKITEXT_AT = ("https://raw.githubusercontent.com/pytorch/examples/"
                "acc295dc7b90714f1bf47f06004fc19a7fe235c4/word_language_model/data/wikitext-2/")

WIKITEXT = Dataset(
    key="wikitext",
    title="WikiText-2 sentences",
    kind="Text",
    in_fit=True,
    what="One sequence per sentence, one word per event. Every second sentence of the validation "
         "file is learned; the queries come from the test file.",
    licence="CC BY-SA (the text is from Wikipedia)",
    page="https://arxiv.org/abs/1609.07843",
    cite="Merity, Xiong, Bradbury and Socher, Pointer Sentinel Mixture Models, 2016 "
         "(https://arxiv.org/abs/1609.07843); the files as distributed in pytorch/examples",
    downloads=(
        Download(
            url=_WIKITEXT_AT + "valid.txt",
            filename="wikitext-2.valid.txt",
            size=1121681,
            sha256="f0737ed31fc1329026e95cb8b98e19c2a182c39c240ab909dc31abf2f8af58e8",
        ),
        Download(
            url=_WIKITEXT_AT + "test.txt",
            filename="wikitext-2.test.txt",
            size=1256449,
            sha256="d790b833ef8cf03a90db7bf1271b7520b83c45ce07ba3c1a9699df81e239eca0",
        ),
    ),
    read=_wikitext,
)

BPI2012 = Dataset(
    key="bpi2012",
    title="Loan applications (BPI Challenge 2012)",
    kind="Finance",
    in_fit=False,
    what="One sequence per loan application: the steps of its handling in order, each event an "
         "activity with its lifecycle state (36 symbols). "
         "Two applications in four are learned, one in four held out.",
    licence="4TU General Terms of Use (https://doi.org/10.4121/resource:terms_of_use)",
    page="https://doi.org/10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f",
    cite="BPI Challenge 2012, 4TU.ResearchData, doi:10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f",
    downloads=(Download(
        url="https://data.4tu.nl/file/533f66a4-8911-4ac7-8612-1235d65d1f37/3276db7f-8bee-4f2b-88ee-92dbffb5a893",
        filename="BPI_Challenge_2012.xes.gz",
        size=3342406,
        sha256="5cd9cc16b9bcb20bd4aae45666a5d87479ddbf47e6371618b6ad217174cecdf3",
    ),),
    read=_bpi2012,
)

SEPSIS = Dataset(
    key="sepsis",
    title="Hospital pathways of sepsis cases",
    kind="Healthcare",
    in_fit=False,
    what="One sequence per patient: the activities recorded on the way through the hospital, in "
         "order (16 activities). Four cases in five are learned, one in five held out.",
    licence="4TU General Terms of Use (https://doi.org/10.4121/resource:terms_of_use)",
    page="https://doi.org/10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460",
    cite="Mannhardt, Sepsis Cases - Event Log, 4TU.ResearchData, 2016, "
         "doi:10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460",
    downloads=(Download(
        url="https://data.4tu.nl/file/33632f3c-5c48-40cf-8d8f-2db57f5a6ce7/643dccf2-985a-459e-835c-a82bce1c0339",
        filename="Sepsis_Cases_Event_Log.xes.gz",
        size=202508,
        sha256="709c52340306415952811b9b9c5dc6bcc8f8d47d583eba39df9a538459dc543a",
    ),),
    read=_sepsis,
)

BACH = Dataset(
    key="bach",
    title="Bach chorale chord progressions",
    kind="Music",
    in_fit=False,
    what="One sequence per chorale: its chords in order, repeats of a sounding chord merged "
         "(60 chorales, 102 chord labels). Four chorales in five are learned, one in five held out.",
    licence="CC BY 4.0",
    page="https://doi.org/10.24432/C5B61F",
    cite="Radicioni and Esposito, Bach Choral Harmony, UCI Machine Learning Repository, 2014, "
         "doi:10.24432/C5B61F",
    downloads=(Download(
        url="https://archive.ics.uci.edu/static/public/298/bach+choral+harmony.zip",
        filename="bach_choral_harmony.zip",
        size=42978,
        members=(("jsbach_chorals_harmony.data",
                  "81554b251ca9183686b0aa207f214ea92fd48dbb73ef89fa1678a257d3a57457"),),
    ),),
    read=_bach,
)

UNIX = Dataset(
    key="unix",
    title="UNIX shell sessions",
    kind="Computing",
    in_fit=False,
    what="One sequence per shell session of eight users: command names, flags and shell "
         "metacharacters in order, file names replaced by a count. Every second session is "
         "learned, one in ten held out.",
    licence="CC BY 4.0 on the UCI page. The README in the archive is stricter: research use only, "
            "no literal tokens or token sequences published, not part of a commercial product",
    page="https://doi.org/10.24432/C5302K",
    cite="Lane, UNIX User Data, UCI Machine Learning Repository, doi:10.24432/C5302K",
    downloads=(Download(
        url="https://archive.ics.uci.edu/static/public/141/unix+user+data.zip",
        filename="unix_user_data.zip",
        size=164996,
        members=(("UNIX_user_data.tar.gz",
                  "3aabaaebce9c30e008ad65ad3dd9b1916d85f03b3272b28f59d980e9f6821ee8"),),
    ),),
    read=_unix,
)

DATASETS = {d.key: d for d in (HDFS, MSNBC, WIKITEXT, BPI2012, SEPSIS, BACH, UNIX)}
