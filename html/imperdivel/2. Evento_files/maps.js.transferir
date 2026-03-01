jQuery(document).ready(function($) {
    'use strict';

    var mapObject = $('#map-object');
    if (mapObject.length === 0) {
        return;
    }

    var mapCenter = new google.maps.LatLng(mapObject.data('latitude'), mapObject.data('longitude'));
    var styles = mapObject.data('styles');
    var zoom = mapObject.data('zoom');
    var showAllMarkers = mapObject.data('show-all-markers');
    var cluster = [{
        height: 36,
        width: 36
    }];
    var mapOptions = {
        zoom: zoom,
        styles: styles,
        center: mapCenter,
        scrollwheel: false,
        mapTypeControl: false,
        streetViewControl: false,
        zoomControl: false,
        mapTypeId: google.maps.MapTypeId.ROADMAP
    };

    var map = new google.maps.Map(document.getElementById('map-object'), mapOptions);
    var markerClusterer = new MarkerClusterer(map, markers, {styles: cluster});
    var markers = [];

    var data = {
        'action': 'listing_manager_filter_listings',
        'orderby': mapObject.data('orderby'),
        'max-pins': mapObject.data('max-pins'),
        'marker-style': mapObject.data('marker-style')
    };

    if (mapObject.data('ids')) {
        data['ids'] = mapObject.data('ids');
    }

    var infobox = new InfoBox({
        content: 'empty',
        disableAutoPan: false,
        maxWidth: 0,
        pixelOffset: new google.maps.Size(-250, -330),
        zIndex: null,
        closeBoxURL: "",
        infoBoxClearance: new google.maps.Size(1, 1),
        isHidden: false,
        isOpen: false,
        pane: "floatPane",
        enableEventPropagation: false
    });

    // Close infobox event
    infobox.addListener('domready', function () {
        $('.infobox-close').on('click', function () {
            infobox.close(map, this);
            infobox.isOpen = false;
        });
    });

    // Autosubmit live filtering map
    $('form.auto-submit-filter :input').on('change', function(e) {
        if ($(this).closest('.map-wrapper').find('.map-container').hasClass('filter-live')) {
            reloadData();
        }
    });

    // Live filter
    $('.map-container.filter-live').closest('.map-wrapper').find('form').on('submit', function(e) {
        e.preventDefault();
        reloadData();
    });

    reloadData();

    function reloadData() {
        var fields = '';

        if (mapObject.hasClass('filter-live')) {
            fields = mapObject.closest('.map-wrapper').find('form').serialize();
        }

        $.ajax({
            url: mapObject.data('ajax-action'),
            data: $.param( data ) + '&' + fields,
            success: function(data) {
                var bounds = new google.maps.LatLngBounds();

                markerClusterer.setMap(null)
                $.each(markers, function(index, marker) {
                    marker.setMap(null);
                });
                markers = [];

                $.each(data, function (index, value) {
                    var markerCenter = new google.maps.LatLng(value.latitude, value.longitude);
                    var markerTemplate = value.marker;

                    var marker = new RichMarker({
                        id: value.id,
                        data: value,
                        flat: true,
                        position: markerCenter,
                        map: map,
                        shadow: 0,
                        content: markerTemplate
                    });

                    markers.push(marker);

                    google.maps.event.addListener(marker, 'click', function () {
                        var c = value.infobox;

                        if (!infobox.isOpen) {
                            infobox.setContent(c);
                            infobox.open(map, this);
                            infobox.isOpen = true;
                            infobox.markerId = marker.id;
                        } else {
                            if (infobox.markerId == marker.id) {
                                infobox.close(map, this);
                                infobox.isOpen = false;
                            } else {
                                infobox.close(map, this);
                                infobox.isOpen = false;

                                infobox.setContent(c);
                                infobox.open(map, this);
                                infobox.isOpen = true;
                                infobox.markerId = marker.id;
                            }
                        }
                    });

                    bounds.extend(new google.maps.LatLng(value.latitude, value.longitude));
                });

                if (showAllMarkers === 'on') {
                    map.fitBounds(bounds);
                }

                markerClusterer = new MarkerClusterer(map, markers, {styles: cluster});
            }
        });
    }

    $('#map-control-zoom-in').on('click', function(e) {
        e.preventDefault();
        var zoom = map.getZoom();
        map.setZoom(zoom + 1);
    });

    $('#map-control-zoom-out').on('click', function(e) {
        e.preventDefault();
        var zoom = map.getZoom();
        map.setZoom(zoom - 1);
    });

    $('#map-control-type-roadmap').on('click', function(e) {
        e.preventDefault();
        map.setMapTypeId(google.maps.MapTypeId.ROADMAP);
    });

    $('#map-control-type-terrain').on('click', function(e) {
        e.preventDefault();
        map.setMapTypeId(google.maps.MapTypeId.TERRAIN);
    });

    $('#map-control-type-satellite').on('click', function(e) {
        e.preventDefault();
        map.setMapTypeId(google.maps.MapTypeId.SATELLITE);
    });

    $('#map-control-current-position').on('click', function(e) {
        e.preventDefault();

        $('input[name=filter-geolocation]').attr('value', 'Loading address...');

        navigator.geolocation.getCurrentPosition(function (position) {
            var initialLocation = new google.maps.LatLng(position.coords.latitude, position.coords.longitude);
            map.setCenter(initialLocation);

            $('input[name=filter-distance-latitude]').attr('value', position.coords.latitude);
            $('input[name=filter-distance-longitude]').attr('value', position.coords.longitude);
            addressFromPosition(position);
        }, function () {
            // map.center = new google.maps.LatLng(settings.center.latitude, settings.center.longitude);
        });
    });
});