"""Tests for the package analyzer."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_mcp.core.package import (
    ModuleInfo,
    PackageAnalyzer,
    PackageMetadata,
    analyze_installed_package,
)


# Helper to create a mock module
def create_mock_module(name: str, is_package: bool = False) -> types.ModuleType:
    """Create a mock module for testing."""
    module = types.ModuleType(name)
    module.__name__ = name
    if is_package:
        module.__path__ = [f"/fake/path/{name}"]
    return module


# Helper to create a mock package with submodules
def create_mock_package(name: str, submodules: list[str] | None = None) -> types.ModuleType:
    """Create a mock package with submodules."""
    package = create_mock_module(name, is_package=True)
    package.__all__ = ["public_func"]

    def public_func(x: int) -> int:
        """A public function."""
        return x * 2

    package.public_func = public_func
    return package


class TestModuleInfo:
    """Tests for ModuleInfo dataclass."""

    def test_module_info_creation(self) -> None:
        """Test creating a ModuleInfo instance."""
        module = create_mock_module("test_module")
        info = ModuleInfo(
            name="test_module",
            module=module,
            is_package=False,
            is_public=True,
        )

        assert info.name == "test_module"
        assert info.module is module
        assert info.is_package is False
        assert info.is_public is True
        assert info.parent is None
        assert info.submodules == []

    def test_module_info_with_parent_and_submodules(self) -> None:
        """Test ModuleInfo with parent and submodules."""
        module = create_mock_module("parent.child")
        info = ModuleInfo(
            name="parent.child",
            module=module,
            is_package=True,
            is_public=True,
            parent="parent",
            submodules=["parent.child.sub1", "parent.child.sub2"],
        )

        assert info.parent == "parent"
        assert len(info.submodules) == 2
        assert "parent.child.sub1" in info.submodules


class TestPackageMetadata:
    """Tests for PackageMetadata dataclass."""

    def test_package_metadata_creation(self) -> None:
        """Test creating a PackageMetadata instance."""
        module = create_mock_package("test_pkg")
        metadata = PackageMetadata(
            name="test_pkg",
            root_module=module,
        )

        assert metadata.name == "test_pkg"
        assert metadata.root_module is module
        assert metadata.module_count == 0
        assert metadata.public_module_count == 0
        assert metadata.method_count == 0

    def test_package_metadata_counts(self) -> None:
        """Test PackageMetadata count properties."""
        module = create_mock_package("test_pkg")
        metadata = PackageMetadata(
            name="test_pkg",
            root_module=module,
        )

        # Add some modules
        metadata.modules["test_pkg"] = ModuleInfo(
            name="test_pkg",
            module=module,
            is_package=True,
            is_public=True,
        )
        metadata.modules["test_pkg.sub"] = ModuleInfo(
            name="test_pkg.sub",
            module=create_mock_module("test_pkg.sub"),
            is_package=False,
            is_public=False,
        )

        assert metadata.module_count == 2
        assert metadata.public_module_count == 1


class TestPackageAnalyzer:
    """Tests for PackageAnalyzer."""

    def test_analyzer_initialization(self) -> None:
        """Test PackageAnalyzer initialization."""
        analyzer = PackageAnalyzer()
        assert analyzer.include_private is False
        assert analyzer.max_depth is None
        assert analyzer.follow_imports is False

    def test_analyzer_with_options(self) -> None:
        """Test PackageAnalyzer with custom options."""
        analyzer = PackageAnalyzer(
            include_private=True,
            max_depth=3,
            follow_imports=True,
        )
        assert analyzer.include_private is True
        assert analyzer.max_depth == 3
        assert analyzer.follow_imports is True

    def test_load_package_from_string(self) -> None:
        """Test loading a package by string name."""
        analyzer = PackageAnalyzer()

        # json is a standard library package
        module = analyzer._load_package("json")
        assert module.__name__ == "json"
        assert hasattr(module, "__path__")

    def test_load_package_from_module(self) -> None:
        """Test loading a package from module object."""
        import json

        analyzer = PackageAnalyzer()
        module = analyzer._load_package(json)
        assert module is json

    def test_load_package_fails_for_non_package(self) -> None:
        """Test that loading a non-package module raises ValueError."""
        # math is a module, not a package
        analyzer = PackageAnalyzer()
        with pytest.raises(ValueError, match="is a module, not a package"):
            analyzer._load_package("math")

    def test_load_package_fails_for_nonexistent(self) -> None:
        """Test that loading a non-existent package raises ImportError."""
        analyzer = PackageAnalyzer()
        with pytest.raises(ImportError):
            analyzer._load_package("nonexistent_package_12345")

    def test_analyze_json_package(self) -> None:
        """Test analyzing the json package (stdlib)."""
        analyzer = PackageAnalyzer()
        metadata = analyzer.analyze_package("json")

        assert metadata.name == "json"
        assert metadata.module_count >= 1
        assert metadata.method_count > 0

    def test_analyze_with_max_depth(self) -> None:
        """Test analyzing with max_depth limit."""
        analyzer = PackageAnalyzer(max_depth=0)
        metadata = analyzer.analyze_package("json")

        # With max_depth=0, should only analyze root module
        assert metadata.module_count == 1

    def test_extract_public_api(self) -> None:
        """Test extracting public API from __all__."""
        package = create_mock_package("test_pkg")
        package.__all__ = ["func1", "func2"]

        analyzer = PackageAnalyzer()
        public_api = analyzer._extract_public_api(package)

        assert "test_pkg.func1" in public_api
        assert "test_pkg.func2" in public_api

    def test_matches_patterns_no_patterns(self) -> None:
        """Test pattern matching with no patterns."""
        analyzer = PackageAnalyzer()
        assert analyzer._matches_patterns("any.module", None, None) is True

    def test_matches_patterns_include(self) -> None:
        """Test pattern matching with include patterns."""
        analyzer = PackageAnalyzer()

        assert analyzer._matches_patterns(
            "json.decoder",
            include_patterns=["json.*"],
            exclude_patterns=None,
        ) is True

        assert analyzer._matches_patterns(
            "xml.parser",
            include_patterns=["json.*"],
            exclude_patterns=None,
        ) is False

    def test_matches_patterns_exclude(self) -> None:
        """Test pattern matching with exclude patterns."""
        analyzer = PackageAnalyzer()

        assert analyzer._matches_patterns(
            "json.decoder",
            include_patterns=None,
            exclude_patterns=["*.decoder"],
        ) is False

        assert analyzer._matches_patterns(
            "json.encoder",
            include_patterns=None,
            exclude_patterns=["*.decoder"],
        ) is True

    def test_matches_patterns_both(self) -> None:
        """Test pattern matching with both include and exclude patterns."""
        analyzer = PackageAnalyzer()

        # Include json.* but exclude *.decoder
        assert analyzer._matches_patterns(
            "json.encoder",
            include_patterns=["json.*"],
            exclude_patterns=["*.decoder"],
        ) is True

        # json.decoder is excluded
        assert analyzer._matches_patterns(
            "json.decoder",
            include_patterns=["json.*"],
            exclude_patterns=["*.decoder"],
        ) is False

    def test_is_module_public_with_public_api(self) -> None:
        """Test checking if module is public via __all__."""
        analyzer = PackageAnalyzer()
        public_api = {"pkg.mod1", "pkg.mod1.func1"}

        assert analyzer._is_module_public("pkg.mod1", public_api) is True
        assert analyzer._is_module_public("pkg.mod2", public_api) is True  # No private indicator

    def test_is_module_public_private_name(self) -> None:
        """Test that private modules are detected."""
        analyzer = PackageAnalyzer()
        public_api: set[str] = set()

        # _private is private
        assert analyzer._is_module_public("pkg._private", public_api) is False

        # __dunder__ is not private
        assert analyzer._is_module_public("pkg.__dunder__", public_api) is True

    def test_get_public_methods(self) -> None:
        """Test getting only public methods."""
        analyzer = PackageAnalyzer()
        metadata = analyzer.analyze_package("json")

        public_methods = analyzer.get_public_methods(metadata)
        # All returned methods should be marked as public API
        for method in public_methods:
            assert method.mcp_metadata.get("is_public_api") is True

    def test_get_methods_by_module(self) -> None:
        """Test grouping methods by module."""
        analyzer = PackageAnalyzer()
        metadata = analyzer.analyze_package("json")

        by_module = analyzer.get_methods_by_module(metadata)

        # Should have at least the json module
        assert "json" in by_module
        assert len(by_module["json"]) > 0


class TestAnalyzeInstalledPackage:
    """Tests for the convenience function."""

    def test_analyze_installed_package(self) -> None:
        """Test the convenience function."""
        metadata = analyze_installed_package("json")

        assert metadata.name == "json"
        assert metadata.module_count >= 1

    def test_analyze_with_options(self) -> None:
        """Test convenience function with options."""
        metadata = analyze_installed_package(
            "json",
            include_private=False,
            max_depth=1,
        )

        assert metadata.name == "json"


class TestPackageAnalyzerWithPatterns:
    """Tests for package analysis with include/exclude patterns."""

    def test_include_pattern(self) -> None:
        """Test analyzing with include pattern."""
        analyzer = PackageAnalyzer()
        metadata = analyzer.analyze_package(
            "json",
            include_patterns=["json"],  # Only root
        )

        # Should only include the root json module
        assert "json" in metadata.modules

    def test_exclude_pattern(self) -> None:
        """Test analyzing with exclude pattern."""
        analyzer = PackageAnalyzer()
        metadata = analyzer.analyze_package(
            "json",
            exclude_patterns=["json.decoder"],
        )

        # json.decoder should not be in modules
        assert "json.decoder" not in metadata.modules

    def test_matches_patterns_allows_parent_traversal(self) -> None:
        """Test that include patterns allow traversing through parent modules.

        When using '--include pkg.sub.*', the parent 'pkg' should be traversed
        so that 'pkg.sub' can be discovered.
        """
        analyzer = PackageAnalyzer()

        # Pattern 'json.decoder.*' should allow traversing 'json'
        assert analyzer._matches_patterns(
            "json",
            include_patterns=["json.decoder.*"],
            exclude_patterns=None,
        ) is True

        # And also allow 'json.decoder' itself
        assert analyzer._matches_patterns(
            "json.decoder",
            include_patterns=["json.decoder.*"],
            exclude_patterns=None,
        ) is True

        # But not unrelated modules
        assert analyzer._matches_patterns(
            "xml",
            include_patterns=["json.decoder.*"],
            exclude_patterns=None,
        ) is False

    def test_module_matches_for_methods_star_includes_parent(self) -> None:
        """Test that '.*' patterns also match their parent module.

        When using '--include pkg.sub.*', methods from 'pkg.sub' itself
        should be included (not just submodules like 'pkg.sub.foo').
        """
        analyzer = PackageAnalyzer()

        # Pattern 'json.decoder.*' should include methods from 'json.decoder'
        assert analyzer._module_matches_for_methods(
            "json.decoder",
            include_patterns=["json.decoder.*"],
            exclude_patterns=None,
        ) is True

        # And also 'json.decoder.something'
        assert analyzer._module_matches_for_methods(
            "json.decoder.something",
            include_patterns=["json.decoder.*"],
            exclude_patterns=None,
        ) is True

        # But not the parent 'json' (only traversed, not included)
        assert analyzer._module_matches_for_methods(
            "json",
            include_patterns=["json.decoder.*"],
            exclude_patterns=None,
        ) is False

    def test_module_matches_for_methods_no_patterns(self) -> None:
        """Test that no patterns means all modules are included."""
        analyzer = PackageAnalyzer()

        assert analyzer._module_matches_for_methods(
            "any.module",
            include_patterns=None,
            exclude_patterns=None,
        ) is True

    def test_module_matches_for_methods_exclude(self) -> None:
        """Test that exclude patterns are respected."""
        analyzer = PackageAnalyzer()

        assert analyzer._module_matches_for_methods(
            "json.decoder",
            include_patterns=None,
            exclude_patterns=["*.decoder"],
        ) is False

        assert analyzer._module_matches_for_methods(
            "json.encoder",
            include_patterns=None,
            exclude_patterns=["*.decoder"],
        ) is True


class TestPackageAnalyzerPrivateModules:
    """Tests for private module handling."""

    def test_exclude_private_by_default(self) -> None:
        """Test that private modules are excluded by default."""
        analyzer = PackageAnalyzer(include_private=False)

        # The _matches_patterns function should handle this
        # A module starting with _ should be skipped
        assert analyzer._is_module_public("pkg._internal", set()) is False

    def test_include_private_when_enabled(self) -> None:
        """Test that private modules can be included."""
        analyzer = PackageAnalyzer(include_private=True)

        # With include_private=True, even _internal should be analyzed
        # This is controlled by the should_include check in _discover_modules
        assert analyzer.include_private is True


class TestPackageAnalyzerFromPath:
    """Tests for analyze_package_file."""

    def test_analyze_from_path_not_dir(self, tmp_path: Path) -> None:
        """Test error when path is not a directory."""
        analyzer = PackageAnalyzer()

        file_path = tmp_path / "not_a_dir.py"
        file_path.touch()

        with pytest.raises(ValueError, match="must be a directory"):
            analyzer.analyze_package_file(file_path)

    def test_analyze_from_path_no_init(self, tmp_path: Path) -> None:
        """Test error when directory has no __init__.py."""
        analyzer = PackageAnalyzer()

        pkg_dir = tmp_path / "not_a_package"
        pkg_dir.mkdir()

        with pytest.raises(ValueError, match="Not a valid Python package"):
            analyzer.analyze_package_file(pkg_dir)

    def test_analyze_from_path_success(self, tmp_path: Path) -> None:
        """Test successful analysis from path."""
        analyzer = PackageAnalyzer()

        # Create a simple package
        pkg_dir = tmp_path / "my_test_package"
        pkg_dir.mkdir()
        init_file = pkg_dir / "__init__.py"
        init_file.write_text("def sample_func():\n    pass\n")

        metadata = analyzer.analyze_package_file(pkg_dir)

        assert metadata.name == "my_test_package"
        assert "my_test_package" in metadata.modules
