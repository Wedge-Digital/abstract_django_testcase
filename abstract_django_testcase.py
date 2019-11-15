import abc
import datetime
import errno
import inspect
import os
import json
from decimal import Decimal
from os import path
from shutil import which
from django.test import TestCase
from django.conf import settings


class AbstractTestCase(abc.ABC, TestCase):
    """
    Abstract class to handle common functionality

    ROOT_DIR must be define in django settings file like this:
        ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    """

    _fixture_dir = None

    @classmethod
    def get_test_fixtures_dir(cls) -> str:
        """
        Get fixtures directory

        Returns:
            str: fixtures directory
        """
        if not cls._fixture_dir:
            filename = cls._get_calling_filename()
            pos = filename.find("/tests")
            if not pos > 0:
                raise ValueError(f"Unable to determine root tests path from {filename}")
            cls._fixture_dir = f"{filename[:pos]}/tests/fixtures"

        return cls._fixture_dir

    @classmethod
    def get_resultsets_dir(cls) -> str:
        """
        Get result sets dir

        Returns:
            str: result sets directory
        """
        return f"{cls.get_test_fixtures_dir()}/resultsets"

    @classmethod
    def get_datasets_dir(cls, filename) -> str:
        """
        get data sets path

        Args:
            filename (str): related path of filename

        Returns:
            str: data sets directory
        """
        return f"{cls.get_test_fixtures_dir()}/datasets/{filename}"

    @classmethod
    def get_common_datasets_dir(cls, filename) -> str:
        """
        get common data sets path

        Args:
            filename (str): related path of filename

        Returns:
            str: common data sets directory
        """
        common_dir = os.path.dirname(os.path.realpath(__file__))
        common_dir = os.path.realpath(f"{common_dir}/../tests/fixtures")
        return f"{common_dir}/datasets/{filename}"

    @classmethod
    def _get_dataset(cls, dataset, dataset_filename):
        """
        Get fixture dataset
        Args:
            dataset(str): relative path to dataset.
                          If is json, load it else just read it

        Returns:
            mixed
        """
        filename, file_extension = os.path.splitext(dataset)
        with open(dataset_filename) as file:
            if file_extension == ".json":
                return json.load(file)
            return file.read()

    @classmethod
    def get_dataset(cls, dataset):
        """
        Get fixture dataset
        Args:
            dataset(str): relative path to dataset.
                          If is json, load it else just read it

        Returns:
            mixed
        """
        return cls._get_dataset(dataset, cls.get_datasets_dir(dataset))

    @classmethod
    def get_common_dataset(cls, dataset):
        """
        Get fixture from common dataset
        Args:
            dataset(str): relative path to dataset.
                          If is json, load it else just read it

        Returns:
            mixed
        """
        return cls._get_dataset(dataset, cls.get_common_datasets_dir(dataset))

    @classmethod
    def get_sandbox_dir(cls, filename=None) -> str:
        """
        Get sandbox dir

        Returns:
            str
        """
        path = f"{cls.get_test_fixtures_dir()}/sandbox"
        if filename is None:
            return path
        return f"{path}/{filename}"

    @classmethod
    def clean_sandbox(cls):
        """
        Clean sandbox
        """
        if not os.path.exists(cls.get_sandbox_dir()):
            os.makedirs(cls.get_sandbox_dir())
        cls._empty_dir(cls.get_sandbox_dir())

    @classmethod
    def get_mock_calls(cls, mock):
        """
        Get mock calls
        Args:
            mock(MagicMock|dict): mock or mock list

        Returns:
            list|dict
        """
        if isinstance(mock, dict):
            calls = {}
            for method, mock in mock.items():
                calls[method] = cls.get_mock_calls(mock)
            return calls

        calls = []
        if mock.call_count > 0:
            for call in mock.call_args_list:
                args, kwargs = call
                calls.append({"args": list(args), "kwargs": kwargs})
            return calls

        for call in mock.method_calls:
            method, args, kwargs = call
            calls.append({"method": method, "args": list(args), "kwargs": kwargs})

        return calls

    def assert_equals_resultset(self, actual, **kwargs):
        """
        assert result set equality

        Build resultset name from filename.
        Compare expected to resultset for tests method
        """

        # build resultset filename from caller filename
        calling_filename = kwargs.get("calling_filename", None)
        filename = self._get_calling_filename()
        calling_frame = self._get_calframe(calling_filename)
        method_name = self._get_calling_method_name(calling_frame)
        sub_dir = self._get_test_subdir(filename)
        filename = calling_filename if calling_filename else filename
        filename_noext = path.basename(filename).replace(".py", "")
        resultset_filename = (
            f"{self.get_resultsets_dir()}/{sub_dir}/{filename_noext}/{method_name}.json"
        )
        self._check_file_can_be_created(resultset_filename)

        # get expected result sets from file
        if os.path.exists(resultset_filename):
            with open(resultset_filename) as json_file:
                expected = json_file.read()
        else:
            # create missing file
            with open(resultset_filename, "w") as f:
                json.dump({}, f)
                expected = None

        actual_json = (
            json.dumps(
                self._to_json_dumpable(actual),
                indent=4,
                separators=(",", ": "),
                default=str,
                # disable non-ASCII characters escape with \uXXXX sequences
                ensure_ascii=False,
            )
            + "\n"  # for respecting file empty last line convention
        )
        # assert
        try:
            assert expected == actual_json
        except AssertionError as e:
            working_dir = settings.ROOT_DIR

            # build fix result set
            tmp_actual_filename = (
                f"{working_dir}/.donotcommit_tmp/"
                f"{filename_noext}-{method_name}_ACTUAL.json"
            )
            self._check_file_can_be_created(tmp_actual_filename)

            with open(tmp_actual_filename, "w") as f:
                f.write(actual_json)

            with open(f"{working_dir}/.donotcommit_tmp_diff_cmd", "a+") as f:
                if which("charm") is not None:
                    f.write(f"charm diff {resultset_filename} {tmp_actual_filename}\n")
                elif which("pycharm-community") is not None:
                    f.write(
                        f"pycharm-community diff {resultset_filename} {tmp_actual_filename}\n"
                    )
                elif which("meld") is not None:
                    f.write(f"meld {tmp_actual_filename} {resultset_filename}\n")
                elif which("code") is not None:
                    f.write(f"code -d {tmp_actual_filename} {resultset_filename}\n")

            print(f"\n\033[1;31m=== TEST {method_name} has failed !!")
            print(f"file: {filename.replace(working_dir, '')}")
            os.system(f"diff {resultset_filename} {tmp_actual_filename}")
            print(f"=== TEST {method_name}\n\033[0m")
            raise e

    @staticmethod
    def assert_file_exists(filename):
        assert os.path.exists(filename)

    @staticmethod
    def assert_file_not_exists(filename):
        assert not os.path.exists(filename)

    @classmethod
    def _check_dir_exists(cls, directory) -> None:
        """
        Check if a directory exists

        Args:
            directory(str):

        Returns:
            None if directory exists

        Raises:
            RuntimeError if directory does not exists
        """
        if os.path.isdir(directory):
            return None
        raise RuntimeError(f"{directory} does not exists")

    @classmethod
    def _empty_dir(cls, directory) -> None:
        """
        Empty a directory

        Args:
            directory(str):

        Returns:
            None

        Raises:
            RuntimeError if directory does not exists
        """
        cls._check_dir_exists(directory)
        for root, dirs, files in os.walk(directory, topdown=False):
            for file in files:
                os.remove(os.path.join(root, file))
            if root != directory:
                os.rmdir(root)

    @staticmethod
    def _get_test_subdir(filename):
        """
        Get subdir after tests directory
        Args:
            filename:

        Returns:

        """
        working_dir = settings.ROOT_DIR
        dir_names = path.dirname(filename.replace(working_dir, "")).split("/")

        # search tests dir
        for i in range(0, len(dir_names)):
            dir_name = dir_names.pop(0)
            if dir_name == "tests":
                break

        return "/".join(dir_names)

    @classmethod
    def _get_calframe(cls, calling_filename=None) -> inspect.FrameInfo:
        """
        find calling frame from stack calls
        Returns:
            FrameInfo : frame
        """
        # find calling frame
        calframe = inspect.getouterframes(inspect.currentframe(), 2)
        test_filename = (
            cls._get_calling_filename() if not calling_filename else calling_filename
        )
        for frame in calframe:
            if frame.filename.find(test_filename) >= 0:
                return frame
        raise ValueError("Unable to determine calling frame")

    @classmethod
    def _get_calling_filename(cls) -> str:
        """
        Returns:
            str: calling filename
        """
        return inspect.getfile(cls)

    @staticmethod
    def _get_calling_method_name(frame) -> str:
        """
        Returns:
            str: calling method name
        """
        return frame[3]

    @staticmethod
    def _get_calling_lineno(frame) -> str:
        """
        Returns:
            str: calling line number
        """
        return frame.lineno

    @staticmethod
    def _check_file_can_be_created(filename) -> None:
        """
        create missing directories for filename

        Args:
            filename (str) : fullpath filename

        Returns:
            None
        """
        if not os.path.exists(filename):
            try:
                os.makedirs(os.path.dirname(filename))
            except OSError as exc:  # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

    @classmethod
    def _to_json_dumpable(cls, data):
        """ Convert data to be json dumpable """
        if isinstance(data, Decimal):
            return float(data)

        if isinstance(data, datetime.datetime):
            return data.strftime("%Y-%m-%d %H:%M:%S.%f")

        if isinstance(data, datetime.date):
            return data.strftime("%Y-%m-%d")

        if isinstance(data, bytes):
            return data.decode("utf-8")

        if isinstance(data, dict):
            for k, v in data.items():
                data[k] = cls._to_json_dumpable(v)
            return data

        if isinstance(data, list):
            for idx, i in enumerate(data):
                data[idx] = cls._to_json_dumpable(i)
            return data

        if isinstance(data, tuple):
            data = cls._to_json_dumpable(list(data))

        return data
