#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2019 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import division
import sys
import os
import argparse
import pandas as pd
import numpy as np
import plotly.graph_objs as go
import plotly.offline as py

################################################################################


class Plotter:
    def __init__(self, csv_file, include_plotlyjs):
        # DataFrame that stores all csv entries
        self.df_csv = pd.read_csv(
            csv_file, na_values=['None'], keep_default_na=True)
        self.df_csv['Badfix_datetime'] = \
            pd.to_datetime(self.df_csv['Badfix_datetime'], utc=True)
        self.df_csv['Commit_datetime'] = \
            pd.to_datetime(self.df_csv['Commit_datetime'], utc=True)
        self.df_csv.sort_values(by=['Commit_datetime'], inplace=True)
        # See plotly documenation for "include_plotlyjs"
        self.include_plotlyjs = include_plotlyjs
        # Release versions
        self.release_tags = []
        # Version dates
        self.release_dates = []
        # Key: release version, Value: date
        self.mapreltodate = {}
        tags = self.df_csv.Commit_tag.unique()
        for tag in tags:
            df_committags = self.df_csv[self.df_csv['Commit_tag'] == tag]
            date = df_committags.iloc[-1].Commit_datetime.date()
            self.mapreltodate[tag] = date
            self.release_tags.append(tag)
            self.release_dates.append(date)
        # Calculate the "window size" or the min number of commits required
        # when calculating the sliding window regression ratio.
        commits = self.df_csv.shape[0]
        window_size_releases = 10 if len(tags) < 400 else 15
        self.window_size = int((commits / len(tags)) * window_size_releases)

    def plot_regression_events(self, outprefix):
        data = []
        barplots = []
        annotations = []
        df_gtzero = self.df_csv[(self.df_csv['Badfix_lifetime_days'] > 0)]
        newest_date = self.df_csv['Commit_datetime'].max().date()
        release_lifetimes = []
        previous_date = None

        i = -1
        for tag in self.release_tags:
            i += 1
            df_commits = self.df_csv[self.df_csv.Commit_tag == tag]
            df_badfixes = df_gtzero[df_gtzero.Badfix_tag == tag]
            n_commits = df_commits.shape[0]
            n_badfixes = df_badfixes.shape[0]
            release_date = self.mapreltodate.get(tag)
            release_lifetime_days = (newest_date - release_date).days
            release_lifetimes.append(release_lifetime_days)

            if previous_date is not None and release_date == previous_date:
                duplicate_date = True
            else:
                duplicate_date = False

            # Vertical lines for each release
            hovertext =\
                r'<b>%s</b><br \>'\
                r'Date: %s<br \>'\
                r'Lifetime: %s days<br \>'\
                r'Commits: %s<br \>'\
                r'Regressions: %s'\
                % \
                (tag, release_date, release_lifetime_days, n_commits, n_badfixes)
            scatter = go.Scatter(
                x=[release_date, release_date],
                y=[0, release_lifetime_days],
                mode='lines+markers',
                name=tag,
                hovertext=hovertext,
                hoverinfo="text",
                line=dict(dash='dot', color='lightgray', width=1),
                marker=dict(color='lightgray', size=3),
                legendgroup="Release version",
                showlegend=False,
            )
            if duplicate_date:
                plot = data[-1]
                plot.hovertext += r"<br \>---<br \>" + hovertext
            else:
                data.append(scatter)

            # Data volume: number of commits and regressions
            # (show legend only for the first plot)
            showlegend = (i == 0)
            hovertext = \
                r'<b>%s</b><br \>'\
                r'Date: %s<br \>'\
                r'Commits: %s<br \>'\
                r'Regressions: %s'\
                %\
                (tag, release_date, n_commits, n_badfixes)
            bar = go.Bar(
                x=[release_date],
                y=[n_commits],
                width=[1000 * 3600 * 24],
                hovertext=hovertext,
                hoverinfo="text",
                legendgroup='Volume data',
                marker_color='darkgray',
                name='Number of commits',
                xaxis="x1",
                yaxis="y2",
                showlegend=showlegend,
            )
            if duplicate_date:
                plot = barplots[-1]
                plot.hovertext += r"<br \>---<br \>" + hovertext
                plot.y = [plot.y[0] + n_commits]
            else:
                barplots.append(bar)

            # Annotation: release version number
            # (show annotation on every tenth release version)
            if i % 10 == 0:
                annotation = {
                    'x': release_date,
                    'y': release_lifetime_days,
                    'xref': 'x',
                    'yref': 'y',
                    'text': tag,
                    'showarrow': True,
                    'arrowhead': 1,
                    'arrowsize': 0.5,
                    'arrowwidth': 1,
                    'arrowcolor': 'lightgray',
                    'ax': 0,
                }
                annotations.append(annotation)

            previous_date = release_date

        # Release lifetime or "event horizon"
        scatter = go.Scatter(
            x=self.release_dates,
            y=release_lifetimes,
            mode='lines',
            hoverinfo='none',
            name="Release",
            line=dict(dash='dot', color='lightgray'),
        )
        data.append(scatter)

        # Regression markers
        regression_dates = []
        regression_lifetimes = []
        hovertexts = []
        for index, badfix in df_gtzero.iterrows():
            date = badfix['Badfix_datetime'].date()
            lifetime = badfix['Badfix_lifetime_days']
            badfixtag = badfix['Badfix_tag']
            fixedtag = badfix['Commit_tag']
            fixhexsha = badfix['Commit_hexsha']
            badfixhexsha = badfix['Badfix_hexsha']
            regression_dates.append(date)
            regression_lifetimes.append(lifetime)
            hovertext = \
                r'<b>Regression</b><br \>'\
                r'Regression commit: %s<br \>'\
                r'Regression in release: %s<br \>'\
                r'Fix commit: %s<br \>'\
                r'Fixed in release: %s<br \>'\
                r'Regression lifetime: %s days<br \>'\
                %\
                (badfixhexsha[:12], badfixtag, fixhexsha[:12], fixedtag, int(lifetime))
            hovertexts.append(hovertext)
        scatter = go.Scatter(
            x=regression_dates,
            y=regression_lifetimes,
            hovertext=hovertexts,
            hoverinfo=['text'] * len(hovertexts),
            mode='markers',
            name="Regression",
            marker=dict(
                color='rgba(255, 0, 0, 0.4)',
                size=8,
                line=dict(width=1, color='Gray')),
        )
        data.append(scatter)

        # Append barplots here so their legends are shown last
        data.extend(barplots)

        layout = {
            "title": {
                "text": "<b>Regression Events</b>",
                "xref": "paper",
                "x": 0,
            },
            "xaxis1": {
                "title": "Date",
                "showgrid": True,
                "anchor": "y2",
                "tickformat": "%Y-%m-%d",
                "domain": [0.0, 1],
            },
            "yaxis1": {
                "title": "Regression Lifetime (Days)",
                "showgrid": True,
                "anchor": "x2",
                "domain": [0.12, 1.0],
            },
            "yaxis2": {
                "title": "Number of Commits",
                "anchor": "x1",
                "domain": [0.0, 0.12],
            },
            "barmode": "stack",
            "hovermode": "closest",
            "annotations": annotations,
            "template": "plotly_white",
        }

        htmlfilename = outprefix + '__regression_events.html'
        return self._plot_figure(htmlfilename, data, layout)

    def plot_regression_fix_events(self, outprefix):
        data = []
        barplots = []
        annotations = []
        df_gtzero = self.df_csv[(self.df_csv['Badfix_lifetime_days'] > 0)]
        oldest_date = self.df_csv['Commit_datetime'].min().date()
        release_lifetimes = []
        previous_date = None

        i = -1
        for tag in self.release_tags:
            i += 1
            df_commits = self.df_csv[self.df_csv.Commit_tag == tag]
            df_badfix_fixes = df_gtzero[df_gtzero.Commit_tag == tag]
            n_commits = df_commits.shape[0]
            n_badfix_fixes = df_badfix_fixes.shape[0]
            release_date = self.mapreltodate.get(tag)
            days_since_first_release = (release_date - oldest_date).days
            release_lifetimes.append(days_since_first_release)

            if previous_date is not None and release_date == previous_date:
                duplicate_date = True
            else:
                duplicate_date = False

            # Vertical lines for each release
            hovertext =\
                r'<b>%s</b><br \>'\
                r'Date: %s<br \>'\
                r'Days since first release: %s days<br \>'\
                r'Commits: %s<br \>'\
                r'Regression fixes: %s'\
                % \
                (tag, release_date, days_since_first_release, n_commits, n_badfix_fixes)
            scatter = go.Scatter(
                x=[release_date, release_date],
                y=[0, days_since_first_release],
                mode='lines+markers',
                name=tag,
                hovertext=hovertext,
                hoverinfo="text",
                line=dict(dash='dot', color='lightgray', width=1),
                marker=dict(color='lightgray', size=3),
                legendgroup="Release version",
                showlegend=False,
            )
            if duplicate_date:
                plot = data[-1]
                plot.hovertext += r"<br \>---<br \>" + hovertext
            else:
                data.append(scatter)

            # Data volume: number of commits and regression fixes
            # (show legend only for the first plot)
            showlegend = (i == 0)
            hovertext = \
                r'<b>%s</b><br \>'\
                r'Date: %s<br \>'\
                r'Commits: %s<br \>'\
                r'Regression fixes: %s'\
                %\
                (tag, release_date, n_commits, n_badfix_fixes)
            bar = go.Bar(
                x=[release_date],
                y=[n_commits],
                width=[1000 * 3600 * 24],
                hovertext=hovertext,
                hoverinfo="text",
                legendgroup='Volume data',
                marker_color='darkgray',
                name='Number of commits',
                xaxis="x1",
                yaxis="y2",
                showlegend=showlegend,
            )
            if duplicate_date:
                plot = barplots[-1]
                plot.hovertext += r"<br \>---<br \>" + hovertext
                plot.y = [plot.y[0] + n_commits]
            else:
                barplots.append(bar)

            # Annotation: release version number
            # (show annotation on every tenth release version)
            if i % 10 == 0:
                annotation = {
                    'x': release_date,
                    'y': days_since_first_release,
                    'xref': 'x',
                    'yref': 'y',
                    'text': tag,
                    'showarrow': True,
                    'arrowhead': 1,
                    'arrowsize': 0.5,
                    'arrowwidth': 1,
                    'arrowcolor': 'lightgray',
                    'ax': 0,
                }
                annotations.append(annotation)

            previous_date = release_date

        # Release lifetime or "event horizon"
        scatter = go.Scatter(
            x=self.release_dates,
            y=release_lifetimes,
            mode='lines',
            hoverinfo='none',
            name="Release",
            line=dict(dash='dot', color='lightgray'),
        )
        data.append(scatter)

        # Regression fix markers
        regression_fix_dates = []
        regression_lifetimes = []
        hovertexts = []
        for index, badfix in df_gtzero.iterrows():
            date = badfix['Commit_datetime'].date()
            lifetime = badfix['Badfix_lifetime_days']
            badfixtag = badfix['Badfix_tag']
            fixedtag = badfix['Commit_tag']
            fixhexsha = badfix['Commit_hexsha']
            badfixhexsha = badfix['Badfix_hexsha']
            regression_fix_dates.append(date)
            regression_lifetimes.append(lifetime)
            hovertext = \
                r'<b>Regression fix</b><br \>'\
                r'Fix commit: %s<br \>'\
                r'Fixed in release: %s<br \>'\
                r'Regression commit: %s<br \>'\
                r'Regression in release: %s<br \>'\
                r'Regression lifetime: %s days<br \>'\
                %\
                (fixhexsha[:12], fixedtag, badfixhexsha[:12], badfixtag, int(lifetime))
            hovertexts.append(hovertext)
        scatter = go.Scatter(
            x=regression_fix_dates,
            y=regression_lifetimes,
            hovertext=hovertexts,
            hoverinfo=['text'] * len(hovertexts),
            mode='markers',
            name="Regression",
            marker=dict(
                color='rgba(0, 255, 0, 0.4)',
                size=8,
                line=dict(width=1, color='Gray')),
        )
        data.append(scatter)

        # Append barplots here so their legends are shown last
        data.extend(barplots)

        layout = {
            "title": {
                "text": "<b>Regression Fix Events</b>",
                "xref": "paper",
                "x": 0,
            },
            "xaxis1": {
                "title": "Date",
                "showgrid": True,
                "anchor": "y2",
                "tickformat": "%Y-%m-%d",
                "domain": [0.0, 1],
            },
            "yaxis1": {
                "title": "Regression Lifetime (Days)",
                "showgrid": True,
                "anchor": "x2",
                "domain": [0.12, 1.0],
            },
            "yaxis2": {
                "title": "Number of Commits",
                "anchor": "x1",
                "domain": [0.0, 0.12],
            },
            "barmode": "stack",
            "hovermode": "closest",
            "annotations": annotations,
            "template": "plotly_white",
        }

        htmlfilename = outprefix + '__regression_fix_events.html'
        return self._plot_figure(htmlfilename, data, layout)

    def _make_grow(self, pos, listlen, offset):
        def grow(i):
            startidx = pos - i if pos - i > 0 else 0
            stopidx = pos + i + offset if pos + i + offset < listlen else listlen
            return startidx, stopidx
        return grow

    def _sliding_window(self, list_of_numbers, pos=0, limit=0):
        listlen = len(list_of_numbers)
        to_beg = len(list_of_numbers[:pos])
        to_end = len(list_of_numbers[pos + 1:])
        grow_lr = [self._make_grow(pos, listlen, 0),
                   self._make_grow(pos, listlen, 1)]

        for i in range(max(to_beg, to_end) + 1):
            for grow in grow_lr:
                startidx, stopidx = grow(i)
                if startidx == stopidx:
                    sliced = [list_of_numbers[startidx]]
                else:
                    sliced = list_of_numbers[startidx:stopidx]
                if sum(sliced) >= limit:
                    return startidx, startidx + len(sliced)

        return 0, (listlen)

    def plot_badfix_ratio(self, outprefix):
        data = []
        barplots = []
        annotations = []
        n_commits_list = []
        n_badfixes_list = []
        n_badfix_fixes_list = []
        tag_list = []
        df_gtzero = self.df_csv[(self.df_csv['Badfix_lifetime_days'] > 0)]

        previous_date = None
        i = -1
        for tag in self.release_tags:
            i += 1
            df_commits = self.df_csv[self.df_csv.Commit_tag == tag]
            df_badfixes = df_gtzero[df_gtzero.Badfix_tag == tag]
            df_badfix_fixes = df_gtzero[df_gtzero.Commit_tag == tag]
            n_commits = df_commits.shape[0]
            n_badfixes = df_badfixes.shape[0]
            n_badfix_fixes = df_badfix_fixes.shape[0]
            release_date = self.mapreltodate.get(tag)

            if previous_date is not None and release_date == previous_date:
                # We need to make adjustments to the graphs if there
                # is more than one release on the same date. In such cases,
                # we plot the ratios as if the releases that occurred on the
                # same date were in fact the same release (we still indicate the
                # duplicate releases on the hover texts).
                duplicate_date = True
            else:
                duplicate_date = False

            n_badfix_fixes_list.append(n_badfix_fixes)
            n_commits_list.append(n_commits)
            n_badfixes_list.append(n_badfixes)
            tag_list.append(tag)

            # Vertical lines for each release
            hovertext =\
                r'<b>%s</b><br \>'\
                r'Date: %s<br \>'\
                r'Commits: %s<br \>'\
                r'Regressions: %s<br \>'\
                r'Regression fixes: %s'\
                % \
                (tag, release_date, n_commits, n_badfixes, n_badfix_fixes)
            scatter = go.Scatter(
                x=[release_date, release_date],
                y=[0, 0.5],
                mode='lines+markers',
                name=tag,
                hovertext=hovertext,
                hoverinfo="text",
                line=dict(dash='dot', color='lightgray', width=1),
                marker=dict(color='lightgray', size=3),
                legendgroup="Release version",
                showlegend=False,
            )
            if duplicate_date:
                plot = data[-1]
                plot.hovertext += r"<br \>---<br \>" + hovertext
            else:
                data.append(scatter)

            # Data volume: number of commits and regressions
            # (show legend only for the first plot)
            showlegend = (i == 0)
            hovertext = \
                r'<b>%s</b><br \>'\
                r'Date: %s<br \>'\
                r'Commits: %s<br \>'\
                r'Regressions: %s<br \>'\
                r'Regression fixes: %s'\
                %\
                (tag, release_date, n_commits, n_badfixes, n_badfix_fixes)
            bar = go.Bar(
                x=[release_date],
                y=[n_commits],
                width=[1000 * 3600 * 24],
                hovertext=hovertext,
                hoverinfo="text",
                legendgroup='Volume data',
                marker_color='darkgray',
                name='Number of commits',
                xaxis="x1",
                yaxis="y2",
                showlegend=showlegend,
            )
            if duplicate_date:
                plot = barplots[-1]
                plot.hovertext += r"<br \>---<br \>" + hovertext
                plot.y = [plot.y[0] + n_commits]
            else:
                barplots.append(bar)

            # Annotation: release version number
            # (show annotation on every tenth release version)
            if i % 10 == 0:
                annotation = {
                    'x': release_date,
                    'y': 0.5,
                    'xref': 'x',
                    'yref': 'y',
                    'text': tag,
                    'textangle': -45,
                    'showarrow': True,
                    'arrowhead': 1,
                    'arrowsize': 0.5,
                    'arrowwidth': 1,
                    'arrowcolor': 'lightgray',
                    'ax': 0,
                }
                annotations.append(annotation)

            previous_date = release_date

        i = 0
        previous_beg = None
        previous_end = None
        previous_date = None
        ratio_badfix_fix_cumulative_list = []
        ratio_cumulative_list = []
        ratio_badfix_fix_dashed_beg_list = []
        ratio_cumulative_dashed_beg_list = []
        ratio_badfix_fix_dashed_end_list = []
        ratio_cumulative_dashed_end_list = []
        hover_cumulative_list = []
        hover_badfix_fix_list = []
        for tag in self.release_tags:
            release_date = self.mapreltodate.get(tag)
            beg, end = self._sliding_window(n_commits_list, i, self.window_size)
            n_cum_commits = sum(n_commits_list[beg:end])
            n_cum_badfixes = sum(n_badfixes_list[beg:end])
            n_cum_badfix_fixes = sum(n_badfix_fixes_list[beg:end])
            ratio_avg_cumulative = n_cum_badfixes / n_cum_commits
            ratio_avg_badfix_fix_cumulative = n_cum_badfix_fixes / n_cum_commits

            dashed_beg = (previous_beg is None or (beg == 0 and previous_beg == 0))
            dashed_end = (end == len(n_commits_list) and end == previous_end)

            if previous_date is not None and release_date == previous_date:
                duplicate_date = True
                ratio_cumulative_list[-1] = ratio_avg_cumulative
                ratio_badfix_fix_cumulative_list[-1] = ratio_avg_badfix_fix_cumulative
                if dashed_beg:
                    if ratio_cumulative_dashed_beg_list:
                        ratio_cumulative_dashed_beg_list[-1] = ratio_avg_cumulative
                    else:
                        ratio_cumulative_dashed_beg_list.append(ratio_avg_cumulative)
                    if ratio_badfix_fix_dashed_beg_list:
                        ratio_badfix_fix_dashed_beg_list[-1] = ratio_avg_badfix_fix_cumulative
                    else:
                        ratio_badfix_fix_dashed_beg_list.append(ratio_avg_badfix_fix_cumulative)
                elif dashed_end:
                    if ratio_cumulative_dashed_end_list:
                        ratio_cumulative_dashed_end_list[-1] = ratio_avg_cumulative
                    else:
                        ratio_cumulative_dashed_end_list.append(ratio_avg_cumulative)
                    if ratio_badfix_fix_dashed_end_list:
                        ratio_badfix_fix_dashed_end_list[-1] = ratio_avg_badfix_fix_cumulative
                    else:
                        ratio_badfix_fix_dashed_end_list.append(ratio_avg_badfix_fix_cumulative)
            else:
                duplicate_date = False
                ratio_cumulative_list.append(ratio_avg_cumulative)
                ratio_badfix_fix_cumulative_list.append(ratio_avg_badfix_fix_cumulative)
                if dashed_beg:
                    ratio_cumulative_dashed_beg_list.append(ratio_avg_cumulative)
                    ratio_badfix_fix_dashed_beg_list.append(ratio_avg_badfix_fix_cumulative)
                elif dashed_end:
                    ratio_cumulative_dashed_end_list.append(ratio_avg_cumulative)
                    ratio_badfix_fix_dashed_end_list.append(ratio_avg_badfix_fix_cumulative)

            window_left_edge = self.mapreltodate.get(tag_list[beg])
            window_right_edge = self.mapreltodate.get(tag_list[int(end) - 1])
            # Hover: Regression ratio cumulative sliding window releases
            hovertext = \
                r'<b>Regression ratio, sliding window</b><br \>'\
                r'Regression ratio: %s<br \>'\
                r'Release: %s <br \>'\
                r'Date: %s<br \>'\
                r'Window left edge: %s<br \>'\
                r'Window right edge: %s<br \>'\
                r'Commits: %s<br \>'\
                r'Regressions: %s'\
                % \
                ('{:.1%}'.format(ratio_avg_cumulative),
                 tag, release_date, window_left_edge, window_right_edge,
                 n_cum_commits, n_cum_badfixes)
            # Hover: Regression fix ratio cumulative sliding window releases
            hovertext_fix = \
                r'<b>Regression fix ratio, sliding window</b><br \>'\
                r'Regression fix ratio: %s<br \>'\
                r'Release: %s <br \>'\
                r'Date: %s<br \>'\
                r'Window left edge: %s<br \>'\
                r'Window right edge: %s<br \>'\
                r'Commits: %s<br \>'\
                r'Regression fixes: %s'\
                % \
                ('{:.1%}'.format(ratio_avg_badfix_fix_cumulative),
                 tag, release_date, window_left_edge, window_right_edge,
                 n_cum_commits, n_cum_badfix_fixes)
            if duplicate_date:
                hover_cumulative_list[-1] += r"<br \>---<br \>" + hovertext
                hover_badfix_fix_list[-1] += r"<br \>---<br \>" + hovertext_fix
            else:
                hover_cumulative_list.append(hovertext)
                hover_badfix_fix_list.append(hovertext_fix)

            previous_date = release_date
            previous_beg = beg
            previous_end = end
            i += 1

        # Regression ratio average over all releases
        regressions = sum(n_badfixes_list)
        regression_fixes = sum(n_badfix_fixes_list)
        commits = sum(n_commits_list)
        avg = regressions / commits
        avg_pct = '{:.1%}'.format(avg)
        hovertext = \
            r'<b>Average regression ratio</b><br \>'\
            r'Regression ratio: %s<br \>'\
            r'Commits: %s<br \>'\
            r'Regressions: %s<br \>'\
            r'Regression fixes: %s<br \>'\
            % \
            (avg_pct, commits, regressions, regression_fixes)
        scatter = go.Scatter(
            x=self.release_dates,
            y=[avg] * len(self.release_tags),
            hovertext=[hovertext] * len(self.release_dates),
            hoverinfo=["text"] * len(self.release_dates),
            line=dict(dash='dashdot', color='rgb(150,150,150)'),
            name=r'Regression ratio <br \>(avg: %s)' % avg_pct,
            mode='lines',
            legendgroup='Badfixes_ratio',
            xaxis="x1",
            yaxis="y1",
        )
        data.append(scatter)

        # Regression ratio cumulative sliding window: dotted beginning
        beg = 0
        end = len(ratio_cumulative_dashed_beg_list)
        uniq_dates_list = pd.Series(self.release_dates).drop_duplicates().tolist()
        scatter = go.Scatter(
            x=uniq_dates_list[beg:end],
            y=ratio_cumulative_dashed_beg_list,
            hovertext=hover_cumulative_list[beg:end],
            hoverinfo="text",
            legendgroup='Cumulative ratio',
            line=dict(dash='dot', color='rgba(26,122,217,0.8)', width=2.5),
            mode='lines',
            xaxis="x1",
            yaxis="y1",
            showlegend=False,
        )
        data.append(scatter)

        # Regression ratio cumulative sliding window: middle
        beg = len(ratio_cumulative_dashed_beg_list) - 1
        end = len(ratio_cumulative_list) - len(ratio_cumulative_dashed_end_list) + 1
        scatter = go.Scatter(
            x=uniq_dates_list[beg:end],
            y=ratio_cumulative_list[beg:end],
            hovertext=hover_cumulative_list[beg:end],
            hoverinfo="text",
            legendgroup='Cumulative ratio',
            line=dict(color='rgba(26,122,217,0.8)', width=2.5),
            name=r'Regression ratio <br \>(sliding window)',
            mode='lines',
            xaxis="x1",
            yaxis="y1",
        )
        data.append(scatter)

        # Regression ratio cumulative sliding window: dotted end
        beg = len(ratio_cumulative_list) - len(ratio_cumulative_dashed_end_list)
        end = beg + len(ratio_cumulative_dashed_end_list)
        scatter = go.Scatter(
            x=uniq_dates_list[beg:end],
            y=ratio_cumulative_dashed_end_list,
            hovertext=hover_cumulative_list[beg:end],
            hoverinfo="text",
            legendgroup='Cumulative ratio',
            line=dict(dash='dot', color='rgba(26,122,217,0.8)', width=2.5),
            mode='lines',
            xaxis="x1",
            yaxis="y1",
            showlegend=False,
        )
        data.append(scatter)

        # Regression fix ratio cumulative sliding window: dotted beginning
        beg = 0
        end = len(ratio_badfix_fix_dashed_beg_list)
        scatter = go.Scatter(
            x=uniq_dates_list[beg:end],
            y=ratio_badfix_fix_dashed_beg_list,
            hovertext=hover_badfix_fix_list[beg:end],
            hoverinfo="text",
            legendgroup='Badfix fix ratio',
            line=dict(dash='dot', color='lightgreen', width=2.5),
            mode='lines',
            xaxis="x1",
            yaxis="y1",
            showlegend=False,
        )
        data.append(scatter)

        # Regression fix ratio cumulative sliding window: middle
        beg = len(ratio_badfix_fix_dashed_beg_list) - 1
        end = len(ratio_badfix_fix_cumulative_list) - len(ratio_badfix_fix_dashed_end_list) + 1
        scatter = go.Scatter(
            x=uniq_dates_list[beg:end],
            y=ratio_badfix_fix_cumulative_list[beg:end],
            hovertext=hover_badfix_fix_list[beg:end],
            hoverinfo="text",
            legendgroup='Badfix fix ratio',
            line=dict(width=2.5, color='lightgreen'),
            name=r'Regression fix ratio <br \>(sliding window)',
            mode='lines',
            xaxis="x1",
            yaxis="y1",
        )
        data.append(scatter)

        # Regression fix ratio cumulative sliding window: dotted end
        beg = len(ratio_badfix_fix_cumulative_list) - len(ratio_badfix_fix_dashed_end_list)
        end = beg + len(ratio_badfix_fix_dashed_end_list)
        scatter = go.Scatter(
            x=uniq_dates_list[beg:end],
            y=ratio_badfix_fix_dashed_end_list,
            hovertext=hover_badfix_fix_list[beg:end],
            hoverinfo="text",
            legendgroup='Badfix fix ratio',
            line=dict(dash='dot', color='lightgreen', width=2.5),
            mode='lines',
            xaxis="x1",
            yaxis="y1",
            showlegend=False,
        )
        data.append(scatter)

        # Append barplots here so the legends are shown last on the list
        data.extend(barplots)

        layout = {
            "title": {
                "text": "<b>Regression/Fix Ratio</b>",
                "xref": "paper",
                "x": 0,
            },
            "xaxis1": {
                "title": "Date",
                "showgrid": True,
                "anchor": "y2",
                "tickformat": "%Y-%m-%d",
                "domain": [0.0, 1],
            },
            "yaxis1": {
                "title": "Regression/Fix Ratio (%)",
                "showgrid": True,
                "anchor": "x2",
                "domain": [0.12, 1.0],
                "tickformat": ",.0%",
            },
            "yaxis2": {
                "title": "Number of Commits",
                "anchor": "x1",
                "domain": [0.0, 0.12],
            },
            "barmode": "stack",
            "hovermode": "closest",
            "annotations": annotations,
            "template": "plotly_white",
        }

        htmlfilename = outprefix + '__badfixratio.html'
        return self._plot_figure(htmlfilename, data, layout)

    def plot_notfound_ratio(self, outprefix):
        df_badfixes = self.df_csv[self.df_csv['Badfix_hexsha'].notnull()]
        df_lifetimes = df_badfixes['Badfix_lifetime_days']
        # Index: lifetime, Value: count of observations (sorted by index)
        lifetime_counts = df_lifetimes.value_counts().sort_index()
        lifetime_list = [0]
        lifetime_count_list = [0]
        cumsum_found_badfixes_list = [0]
        counts_sum = 0
        for lifetime in lifetime_counts.index:
            if lifetime <= 0:
                continue
            lifetime_count = lifetime_counts[lifetime]
            counts_sum = counts_sum + lifetime_count
            cumsum_found_badfixes_list.append(counts_sum)
            lifetime_list.append(lifetime)
            lifetime_count_list.append(lifetime_count)

        i = 0
        hovertexts_1 = []
        hovertexts_2 = []
        hoverinfos = []
        ratio_not_found_badfixes_list = []
        halflife = None
        halfratio = 0
        for cumsum in cumsum_found_badfixes_list:
            notfound = counts_sum - cumsum
            if counts_sum == 0:
                ratio_not_found = 0
            else:
                ratio_not_found = notfound / counts_sum
            ratio_not_found_badfixes_list.append(ratio_not_found)
            hoverinfos.append("x+text")
            pct = '{:.0%}'.format(ratio_not_found)
            lifetime = int(lifetime_list[i])
            if ratio_not_found <= 0.5 and halflife is None:
                halflife = lifetime
                halfratio = ratio_not_found
            hovertext_1 = \
                r'Not found regression: %s<br \>'\
                r'Lifetime: %s days<br \><br \>'\
                r'(On average after %s days, %s of<br \>'\
                r'regressions have not been found)'\
                % \
                (pct, lifetime, lifetime, pct)
            hovertexts_1.append(hovertext_1)
            hovertext_2 = \
                r'Lifetime: %s days<br \>'\
                r'Number of regressions: %s'\
                % \
                (int(lifetime_list[i]), lifetime_count_list[i])
            hovertexts_2.append(hovertext_2)
            i += 1

        data = []
        scatter = go.Scatter(
            x=lifetime_list,
            y=ratio_not_found_badfixes_list,
            hoverinfo=hoverinfos,
            hovertext=hovertexts_1,
            name='Not found regression (%)',
            line=dict(color='rgb(26,122,217)'),
            xaxis="x1",
            yaxis="y1",
        )
        data.append(scatter)

        bar = go.Bar(
            x=lifetime_list,
            y=lifetime_count_list,
            hoverinfo=hoverinfos,
            hovertext=hovertexts_2,
            marker_color='darkgray',
            name='Regression lifetimes',
            xaxis="x1",
            yaxis="y2",
        )
        data.append(bar)

        trace = {
            'x': [halflife, halflife],
            'y': [0, halfratio],
            'mode': 'lines+markers',
            'name': 'Half-life: %s days' % halflife,
            'hoverinfo': "x+text",
            'yaxis': 'y',
            'line': {'color': 'gray', 'width': 2, 'dash': 'dot'},
            'marker': {'color': 'gray', 'size': 6},
            'showlegend': False,
        }
        data.append(trace)

        annotations = []
        annotation = {
            'x': halflife,
            'y': halfratio,
            'xref': 'x',
            'yref': 'y',
            'text': "Half-life: %s days" % halflife,
            'showarrow': True,
            'arrowhead': 1,
            'arrowsize': 0.5,
            'arrowwidth': 1,
            'arrowcolor': 'lightgray',
            'ax': 30,
            'ay': -50,
        }
        annotations.append(annotation)

        layout = {
            "title": {
                "text": "<b>Not Found Regression (%)</b>",
                "xref": "paper",
                "x": 0,
            },
            "xaxis1": {
                "title": "Lifetime (Days)",
                "showgrid": True,
                "dtick": 10,
                "anchor": "y2",
                # xaxis span widthwise
                "domain": [0.0, 1],
            },
            "yaxis1": {
                "title": "Not found regression (%)",
                "anchor": "x2",
                "range": [0, 1],
                "dtick": 0.05,
                "tickformat": ",.0%",
                # yaxis1 span lengthwise
                "domain": [0.20, 1.0],
                "showline": True,
                "linecolor": "Gray",
            },
            "yaxis2": {
                "title": "Regression Lifetimes",
                "anchor": "x1",
                # yaxis2 span lengthwise
                "domain": [0.0, 0.18],
            },
            "annotations": annotations,
            "template": "plotly_white",
        }

        htmlfilename = outprefix + '__badfixnotfound.html'
        return self._plot_figure(htmlfilename, data, layout)

    def plot_lifetime_stable_vs_mainline(self, outprefix):
        # Select only the regressions
        df_badfixes = self.df_csv[self.df_csv['Badfix_hexsha'].notnull()]
        # Drop rows missing 'Badfix_upstream_lifetime_days'
        df_badfixes = df_badfixes.dropna(subset=['Badfix_upstream_lifetime_days'])
        df_le_zero = df_badfixes[df_badfixes['Badfix_lifetime_days'] <= 0]
        df_gt_zero = df_badfixes[df_badfixes['Badfix_lifetime_days'] > 0]

        data = []

        # Hovertexts: LTS lifetime <= 0
        hovertexts = []
        for idx, row in df_le_zero.iterrows():
            hovertext = \
                r'Fix in stable release: %s<br>'\
                r'Fix commit in stable: %s<br>'\
                r'Lifetime in stable: %s<br>'\
                r'Fix commit in mainline: %s<br>'\
                r'Lifetime in mainline: %s<br>'\
                %\
                (
                    row['Commit_tag'],
                    row['Commit_hexsha'][:12],
                    int(round(row['Badfix_lifetime_days'])),
                    row['Commit_upstream_hexsha'][:12],
                    int(round(row['Badfix_upstream_lifetime_days'])),
                )
            hovertexts.append(hovertext)

        # Lifetime markers: LTS lifetime <= 0
        scatter = go.Scatter(
            x=df_le_zero['Badfix_upstream_lifetime_days_decimal'],
            y=df_le_zero['Badfix_lifetime_days_decimal'],
            hovertext=hovertexts,
            hoverinfo=['text'] * len(hovertexts),
            name='stable lifetime <= 0',
            mode='markers',
            marker=dict(
                color='rgba(0,0,255,0.2)',
                size=8,
                line=dict(width=0.7, color='Gray'),
            ),
        )
        data.append(scatter)

        # Hovertexts: LTS lifetime > 0
        hovertexts = []
        for idx, row in df_gt_zero.iterrows():
            hovertext = \
                r'Fix in stable release: %s<br>'\
                r'Fix commit in stable: %s<br>'\
                r'Lifetime in stable: %s<br>'\
                r'Fix commit in mainline: %s<br>'\
                r'Lifetime in mainline: %s<br>'\
                %\
                (
                    row['Commit_tag'],
                    row['Commit_hexsha'][:12],
                    int(round(row['Badfix_lifetime_days'])),
                    row['Commit_upstream_hexsha'][:12],
                    int(round(row['Badfix_upstream_lifetime_days'])),
                )
            hovertexts.append(hovertext)

        # Lifetime markers: LTS lifetime > 0
        scatter = go.Scatter(
            x=df_gt_zero['Badfix_upstream_lifetime_days_decimal'],
            y=df_gt_zero['Badfix_lifetime_days_decimal'],
            hovertext=hovertexts,
            hoverinfo=['text'] * len(hovertexts),
            name='stable lifetime > 0',
            mode='markers',
            marker=dict(
                color='rgba(255,0,0,0.2)',
                size=8,
                line=dict(width=0.5, color='Gray'),
            ),
        )
        data.append(scatter)

        layout = {
            "title": {
                "text": "<b>Regression lifetime stable vs mainline</b>",
            },
            "xaxis1": {
                "title": "Regerssion Lifetime in Mainline (Days)",
                "showgrid": True,
            },
            "yaxis1": {
                "title": "Regression Lifetime in Stable (Days)",
                "showgrid": True,
            },
            "template": "plotly_white",
        }

        htmlfilename = outprefix + '__badfixlifetime_stable_vs_mainline.html'
        return self._plot_figure(htmlfilename, data, layout)

    def plot_summary(self, outprefix, plot_names):
        outname = outprefix + "__summary.html"
        with open(outname, "w") as out:
            out.write("<html><body>\n")
            for html in plot_names:
                html_leaf_filename = os.path.basename(html)
                out.write(
                    "<object data=\"%s\" width=\"100%%\" height=\"100%%\">"
                    "</object>\n<br></br><br></br>\n" % html_leaf_filename)

            out.write("</body></html>\n")
        print("[+] Wrote file: %s" % outname)

    def _plot_figure(self, filename, data, layout):
        fig = go.Figure(data=data, layout=layout)
        ret = py.plot(
            fig,
            show_link=False,
            filename=filename,
            auto_open=False,
            include_plotlyjs=self.include_plotlyjs)
        print("[+] Wrote file: %s" % ret)
        return ret

################################################################################


def getargs():
    desc =\
        "Visualize data generated with badfixstats.py "\
        "by generating a set of html-files with interactive charts."

    epil = "Example: ./%s badfixes.csv" % os.path.basename(__file__)
    parser = argparse.ArgumentParser(description=desc, epilog=epil)

    help = "set the input filename. "
    parser.add_argument('CSV_FILE', nargs=1, help=help)

    help = "set the output file name prefix, default is the input "\
        "filename (CSV_FILE)."
    parser.add_argument('--out', nargs='?', help=help, default='')

    help = "sets how the plotly library is included in the output html, "\
        "defaults to True. For a description of supported options, "\
        "see plotly documentation for \"include_plotlyjs\""
    parser.add_argument('--include_plotlyjs', nargs='?', help=help, default=True)

    return parser.parse_args()

################################################################################


if __name__ == "__main__":
    args = getargs()
    csv_file = args.CSV_FILE[0]
    outprefix = args.out
    plotlyjs = args.include_plotlyjs

    if not os.path.isfile(csv_file):
        sys.stderr.write(
            "Error: file not found or no permissions: %s\n" % csv_file)
        sys.exit(1)

    if not outprefix:
        outprefix = csv_file

    print("[+] Reading: %s" % csv_file)
    plotter = Plotter(csv_file, plotlyjs)
    plot_names = []
    plot_names.append(plotter.plot_regression_events(outprefix))
    plot_names.append(plotter.plot_regression_fix_events(outprefix))
    plot_names.append(plotter.plot_badfix_ratio(outprefix))
    plot_names.append(plotter.plot_notfound_ratio(outprefix))
    plot_names.append(plotter.plot_lifetime_stable_vs_mainline(outprefix))
    plotter.plot_summary(outprefix, plot_names)

################################################################################
