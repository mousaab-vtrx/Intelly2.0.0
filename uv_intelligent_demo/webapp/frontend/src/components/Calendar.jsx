import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

export function Calendar({ selectedDate, onSelectDate, compact = false }) {
  const [currentDate, setCurrentDate] = useState(new Date());

  function getDaysInMonth(date) {
    return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
  }

  function getFirstDayOfMonth(date) {
    return new Date(date.getFullYear(), date.getMonth(), 1).getDay();
  }

  function getPreviousMonth() {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1));
  }

  function getNextMonth() {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1));
  }

  const monthNames = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  const daysInMonth = getDaysInMonth(currentDate);
  const firstDay = getFirstDayOfMonth(currentDate);
  const days = [];

  for (let i = 0; i < firstDay; i++) {
    days.push(null);
  }
  for (let i = 1; i <= daysInMonth; i++) {
    days.push(i);
  }

  const isToday = (day) => {
    if (!day) return false;
    const today = new Date();
    return day === today.getDate() &&
      currentDate.getMonth() === today.getMonth() &&
      currentDate.getFullYear() === today.getFullYear();
  };

  const isSelected = (day) => {
    if (!day) return false;
    const target = selectedDate || new Date();
    return day === target.getDate() &&
      currentDate.getMonth() === target.getMonth() &&
      currentDate.getFullYear() === target.getFullYear();
  };

  return (
    <div className={`calendar ${compact ? "compact" : ""}`}>
      <div className="calendar-header">
        <button onClick={getPreviousMonth} className="calendar-nav">
          <ChevronLeft size={18} />
        </button>
        <h3>{monthNames[currentDate.getMonth()]} {currentDate.getFullYear()}</h3>
        <button onClick={getNextMonth} className="calendar-nav">
          <ChevronRight size={18} />
        </button>
      </div>

      <div className="calendar-weekdays">
        {dayNames.map(day => (
          <div key={day} className="weekday">{day}</div>
        ))}
      </div>

      <div className="calendar-grid">
        {days.map((day, idx) => (
          <div
            key={idx}
            className={`calendar-day ${day ? "active" : "empty"} ${isToday(day) ? "today" : ""} ${isSelected(day) ? "selected" : ""}`}
            onClick={() =>
              day && onSelectDate?.(new Date(currentDate.getFullYear(), currentDate.getMonth(), day))
            }
          >
            {day}
          </div>
        ))}
      </div>
    </div>
  );
}
