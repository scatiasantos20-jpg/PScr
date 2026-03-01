jQuery(document).ready(function($) {
    'use strict';

    $('.listing-manager-google-map-search').each(function() {
        initializeMap($(this));
    });

    function initializeMap(el) {
        var map = {};
        var id = el.attr('id');
        var searchInput = $('body').find('#' + id + '_search');
        var mapCanvas = $('body').find('#' + id);
        var latitude = $('body').find('#' + id + '_latitude');
        var longitude = $('body').find('#' + id + '_longitude');
        var latLng = new google.maps.LatLng(54.800685, -4.130859);
        var zoom = 5;

        // If we have saved values, let's set the position and zoom level
        if (latitude.val().length > 0 && longitude.val().length > 0) {
            latLng = new google.maps.LatLng(latitude.val(), longitude.val());
            zoom = 17;
        }

        // Map
        var mapOptions = {
            center: latLng,
            zoom: zoom
        };

        map = new google.maps.Map(mapCanvas[0], mapOptions);

        // Marker
        var markerOptions = {
            map: map,
            draggable: true,
            title: 'Drag to set the exact location'
        };
        var marker = new google.maps.Marker(markerOptions);

        if (latitude.val().length > 0 && longitude.val().length > 0) {
            marker.setPosition(latLng);
        }

        // Search
        var autocomplete = new google.maps.places.Autocomplete(searchInput[0]);
        autocomplete.bindTo('bounds', map);

        google.maps.event.addListener(autocomplete, 'place_changed', function () {
            var place = autocomplete.getPlace();
            if (!place.geometry) {
                return;
            }

            if (place.geometry.viewport) {
                map.fitBounds(place.geometry.viewport);
            } else {
                map.setCenter(place.geometry.location);
                map.setZoom(17);
            }

            marker.setPosition(place.geometry.location);

            latitude.val(place.geometry.location.lat());
            longitude.val(place.geometry.location.lng());
        });

        $(searchInput).keypress(function (event) {
            if (13 === event.keyCode) {
                event.preventDefault();
            }
        });

        // Allow marker to be repositioned
        google.maps.event.addListener(marker, 'drag', function () {
            latitude.val(marker.getPosition().lat());
            longitude.val(marker.getPosition().lng());
        });

        $('.location_tab').on('click', function() {
            var center = map.getCenter();
            google.maps.event.trigger($("#location-google-map")[0], 'resize');
            map.setCenter(center);
        });
    }
});