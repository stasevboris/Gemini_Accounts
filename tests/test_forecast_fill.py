import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from tests.qt_support import application
from PySide6.QtGui import QPixmap
from widgets import ForecastWidget
from themes import DARK

class ForecastFillTests(unittest.TestCase):
    def test_fill_is_actual_percentage_even_with_time_forecasts(self):
        application()
        for weekly in (False,True):
            for remaining in (.287,.5,1,0):
                widget=ForecastWidget();widget.resize(426,16)
                widget.set_data([{'reset':(datetime.now(timezone.utc)+timedelta(hours=3)).isoformat(),'remaining':.8}],remaining,'#00ff00',DARK,weekly=weekly)
                with patch('widgets.QPainter') as painter:
                    widget.render(QPixmap(426,16))
                fills=[call.args[0] for call in painter.return_value.fillRect.call_args_list if call.args[1].name()=='#00ff00']
                if remaining:
                    self.assertEqual(len(fills),1)
                    self.assertAlmostEqual(fills[0].width()/420,remaining)
                else:self.assertEqual(fills,[])
                marker=painter.return_value.drawLine.call_args_list[0].args[0]
                self.assertAlmostEqual((marker.x()-3)/420,.8)
                widget.deleteLater()

if __name__=='__main__':unittest.main()
