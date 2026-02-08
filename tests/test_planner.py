"""Tests for the planner service."""

from datetime import date, datetime, time, timedelta

import pytest

from orbit import db
from orbit.models import FixedBlock, Settings, Task
from orbit.services import planner


class TestTimeWindow:
    """Tests for TimeWindow class."""

    def test_duration_minutes(self):
        """Test duration calculation."""
        window = planner.TimeWindow(
            start=datetime(2024, 1, 1, 9, 0),
            end=datetime(2024, 1, 1, 10, 30),
        )
        assert window.duration_minutes == 90.0

    def test_contains(self):
        """Test contains check."""
        window = planner.TimeWindow(
            start=datetime(2024, 1, 1, 9, 0),
            end=datetime(2024, 1, 1, 17, 0),
        )

        assert window.contains(datetime(2024, 1, 1, 12, 0))
        assert window.contains(datetime(2024, 1, 1, 9, 0))
        assert not window.contains(datetime(2024, 1, 1, 8, 0))
        assert not window.contains(datetime(2024, 1, 1, 18, 0))

    def test_overlaps(self):
        """Test overlap detection."""
        window1 = planner.TimeWindow(
            start=datetime(2024, 1, 1, 9, 0),
            end=datetime(2024, 1, 1, 12, 0),
        )
        window2 = planner.TimeWindow(
            start=datetime(2024, 1, 1, 11, 0),
            end=datetime(2024, 1, 1, 14, 0),
        )
        window3 = planner.TimeWindow(
            start=datetime(2024, 1, 1, 13, 0),
            end=datetime(2024, 1, 1, 15, 0),
        )

        assert window1.overlaps(window2)
        assert not window1.overlaps(window3)

    def test_intersection(self):
        """Test intersection calculation."""
        window1 = planner.TimeWindow(
            start=datetime(2024, 1, 1, 9, 0),
            end=datetime(2024, 1, 1, 12, 0),
        )
        window2 = planner.TimeWindow(
            start=datetime(2024, 1, 1, 10, 0),
            end=datetime(2024, 1, 1, 14, 0),
        )

        intersection = window1.intersection(window2)

        assert intersection is not None
        assert intersection.start == datetime(2024, 1, 1, 10, 0)
        assert intersection.end == datetime(2024, 1, 1, 12, 0)

    def test_no_intersection(self):
        """Test no intersection."""
        window1 = planner.TimeWindow(
            start=datetime(2024, 1, 1, 9, 0),
            end=datetime(2024, 1, 1, 10, 0),
        )
        window2 = planner.TimeWindow(
            start=datetime(2024, 1, 1, 11, 0),
            end=datetime(2024, 1, 1, 12, 0),
        )

        assert window1.intersection(window2) is None


class TestParseTime:
    """Tests for time parsing."""

    def test_parse_time(self):
        """Test time string parsing."""
        t = planner.parse_time("09:00")
        assert t.hour == 9
        assert t.minute == 0

        t = planner.parse_time("14:30")
        assert t.hour == 14
        assert t.minute == 30


class TestFeasibleWindow:
    """Tests for feasible window calculation."""

    def test_basic_window(self, sample_settings):
        """Test basic window calculation."""
        task = Task(
            title="Test",
            duration_minutes=30,
            open_time_local="10:00",
            close_time_local="16:00",
        )

        today = date.today()
        window = planner.get_task_feasible_window(
            task,
            today,
            time(9, 0),
            time(17, 0),
        )

        assert window is not None
        assert window.start.hour == 10  # Opens at 10
        assert window.end.hour == 16  # Closes at 16

    def test_window_respects_work_hours(self, sample_settings):
        """Test window respects work hours."""
        task = Task(
            title="Test",
            duration_minutes=30,
            open_time_local="06:00",  # Opens early
            close_time_local="22:00",  # Closes late
        )

        today = date.today()
        window = planner.get_task_feasible_window(
            task,
            today,
            time(9, 0),  # Work starts at 9
            time(17, 0),  # Work ends at 17
        )

        assert window is not None
        assert window.start.hour == 9  # Limited by work start
        assert window.end.hour == 17  # Limited by work end

    def test_no_window_if_closes_before_work(self, sample_settings):
        """Test no window if place closes before work starts."""
        task = Task(
            title="Test",
            duration_minutes=30,
            open_time_local="06:00",
            close_time_local="08:00",  # Closes before work
        )

        today = date.today()
        window = planner.get_task_feasible_window(
            task,
            today,
            time(9, 0),
            time(17, 0),
        )

        assert window is None

    def test_no_window_if_duration_too_long(self, sample_settings):
        """Test no window if task duration exceeds available time."""
        task = Task(
            title="Test",
            duration_minutes=480,  # 8 hours
            open_time_local="10:00",
            close_time_local="12:00",  # Only 2 hours available
        )

        today = date.today()
        window = planner.get_task_feasible_window(
            task,
            today,
            time(9, 0),
            time(17, 0),
        )

        assert window is None


class TestFreeWindows:
    """Tests for free window calculation."""

    def test_no_blocks(self):
        """Test free windows with no fixed blocks."""
        day_start = datetime(2024, 1, 1, 9, 0)
        day_end = datetime(2024, 1, 1, 17, 0)

        windows = planner.get_free_windows(day_start, day_end, [])

        assert len(windows) == 1
        assert windows[0].start == day_start
        assert windows[0].end == day_end

    def test_single_block(self):
        """Test free windows with one fixed block."""
        day_start = datetime(2024, 1, 1, 9, 0)
        day_end = datetime(2024, 1, 1, 17, 0)

        block = FixedBlock(
            date=date(2024, 1, 1),
            start_dt=datetime(2024, 1, 1, 12, 0),
            end_dt=datetime(2024, 1, 1, 13, 0),
            title="Lunch",
        )

        windows = planner.get_free_windows(day_start, day_end, [block])

        assert len(windows) == 2
        assert windows[0].start.hour == 9
        assert windows[0].end.hour == 12
        assert windows[1].start.hour == 13
        assert windows[1].end.hour == 17


class TestPriorityScore:
    """Tests for priority score calculation."""

    def test_higher_priority_higher_score(self):
        """Test that higher priority gives higher score."""
        today = date.today()

        task_low = Task(title="Low", priority=1)
        task_high = Task(title="High", priority=4)

        score_low = planner.calculate_priority_score(task_low, today)
        score_high = planner.calculate_priority_score(task_high, today)

        assert score_high > score_low

    def test_due_today_boost(self):
        """Test that due today gets score boost."""
        today = date.today()

        task_due_today = Task(title="Due Today", priority=2, due_date=today)
        task_no_due = Task(title="No Due", priority=2)

        score_due = planner.calculate_priority_score(task_due_today, today)
        score_no_due = planner.calculate_priority_score(task_no_due, today)

        assert score_due > score_no_due


class TestGeneratePlan:
    """Tests for plan generation."""

    def test_requires_home_location(self):
        """Test that plan generation requires home location."""
        settings = Settings()  # No home location

        with pytest.raises(ValueError, match="Home location not set"):
            planner.generate_plan(date.today(), settings)

    def test_generates_plan(self, sample_settings, sample_tasks):
        """Test basic plan generation."""
        today = date.today()

        result = planner.generate_plan(today, sample_settings)

        assert result.plan is not None
        assert result.plan.plan_date == today
        assert len(result.items) > 0

    def test_respects_fixed_blocks(self, sample_settings, sample_tasks, sample_fixed_block):
        """Test that plan respects fixed blocks."""
        today = date.today()

        result = planner.generate_plan(today, sample_settings)

        # Find the fixed block in the schedule
        fixed_items = [i for i in result.items if i.type == "fixed"]
        assert len(fixed_items) == 1
        assert fixed_items[0].title == sample_fixed_block.title

        # No task should overlap with the fixed block
        for item in result.items:
            if item.type == "task":
                task_window = planner.TimeWindow(start=item.start, end=item.end)
                block_window = planner.TimeWindow(
                    start=sample_fixed_block.start_dt,
                    end=sample_fixed_block.end_dt
                )
                assert not task_window.overlaps(block_window)

    def test_includes_travel_segments(self, sample_settings, sample_tasks):
        """Test that plan includes travel segments."""
        today = date.today()

        result = planner.generate_plan(today, sample_settings)

        travel_items = [i for i in result.items if i.type == "travel"]
        # Should have at least one travel segment if there are errands
        errand_count = len([i for i in result.items if i.type == "task" and i.task and i.task.has_location])
        if errand_count > 0:
            assert len(travel_items) > 0

    def test_deterministic_output(self, sample_settings, sample_tasks):
        """Test that same inputs produce same outputs."""
        today = date.today()

        result1 = planner.generate_plan(today, sample_settings)
        result2 = planner.generate_plan(today, sample_settings)

        # Same number of items
        assert len(result1.items) == len(result2.items)

        # Same order
        for i, (item1, item2) in enumerate(zip(result1.items, result2.items)):
            assert item1.title == item2.title
            assert item1.type == item2.type

    def test_calculates_total_travel(self, sample_settings, sample_tasks):
        """Test that total travel is calculated."""
        today = date.today()

        result = planner.generate_plan(today, sample_settings)

        # Should have non-negative travel totals
        assert result.total_travel_km >= 0
        assert result.total_travel_minutes >= 0


class TestGetRouteWaypoints:
    """Tests for route waypoints extraction."""

    def test_includes_home(self, sample_settings, sample_tasks):
        """Test that waypoints include home."""
        today = date.today()

        result = planner.generate_plan(today, sample_settings)
        waypoints = planner.get_route_waypoints(result, sample_settings)

        # First waypoint should be home
        assert waypoints[0][0] == sample_settings.home_lat
        assert waypoints[0][1] == sample_settings.home_lon
